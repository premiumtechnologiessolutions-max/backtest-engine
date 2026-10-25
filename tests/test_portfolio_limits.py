"""No licensed data needed: deterministic shared LIMIT replay contracts."""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.limit_engine import LimitOrder
from norisk_quant.portfolio import PortfolioSettings, validate_portfolio
from norisk_quant.portfolio_limits import run_limit_portfolio


def bars(rows, times=None):
    if times is None:
        times = pd.date_range("2024-01-02T00:00:00Z", periods=len(rows), freq="min")
    return pd.DataFrame(rows, columns=["o", "h", "l", "c"], index=times)


def order(when, name, side, entry, stop, target, expiry=10):
    return LimitOrder(
        placed_at=when, expires_at=when + pd.Timedelta(minutes=expiry),
        side=side, price=entry, stop=stop, target=target, strategy=name,
    )


def test_two_limit_strategies_share_capacity_and_one_fee_per_roundtrip():
    market = bars([[100, 100, 100, 100], [100, 101.5, 99, 100], [100, 100, 100, 100]])
    cfg = PortfolioSettings({"a": 1, "b": 2}, max_open_positions=2, max_total_ounces=3)
    orders = [order(market.index[1], "a", 1, 100, 99, 102),
              order(market.index[1], "b", -1, 100, 101, 98)]
    result = run_limit_portfolio(market, orders, cfg)
    assert len(result.trades) == 2
    assert result.trades["cost"].sum() == pytest.approx(1.2)
    assert result.trades["net_pnl"].sum() == pytest.approx(-4.2)
    assert result.equity["equity"].iloc[-1] == pytest.approx(-4.2)
    assert validate_portfolio(result, cfg)["status"] == "PASSED"


def test_same_entry_bar_target_is_deferred_then_gap_stop():
    times = pd.to_datetime(["2024-01-02T00:00:00Z", "2024-01-02T00:01:00Z",
                            "2024-01-02T00:20:00Z"])
    market = bars([[100, 100, 100, 100], [100, 102, 100, 101], [98, 99, 97, 98]], times)
    cfg = PortfolioSettings({"a": 1}, max_open_positions=1, max_total_ounces=1)
    result = run_limit_portfolio(market, [order(times[1], "a", 1, 100, 99, 101.5)], cfg)
    assert result.uncertain_entry_tp_deferred == 1
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "gap_stop"
    assert trade["exit_price"] == 98
    assert trade["gap_minutes"] == 18
    assert trade["net_pnl"] == pytest.approx(-2.4)


def test_capacity_not_recycled_on_same_minute_and_order_is_rejected_once():
    market = bars([[100, 101, 99, 100], [100, 100, 100, 100]])
    cfg = PortfolioSettings({"a": 1, "b": 1}, max_open_positions=1, max_total_ounces=1)
    result = run_limit_portfolio(market, [
        order(market.index[0], "a", 1, 100, 99, 102),
        order(market.index[0], "b", -1, 100, 101, 98),
    ], cfg)
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["strategy"] == "a"
    assert result.capacity_rejected == 1
    assert result.pending_at_end == 0


def test_subminute_placement_never_fills_earlier_minute():
    market = bars([[100, 100, 100, 100]] * 4)
    at = market.index[1] + pd.Timedelta(milliseconds=500)
    cfg = PortfolioSettings({"a": 1}, max_open_positions=1, max_total_ounces=1)
    result = run_limit_portfolio(market, [order(at, "a", 1, 100, 99, 101)], cfg)
    assert result.trades.iloc[0]["entry_at"] == market.index[2]
    assert result.trades.iloc[0]["signal_at"] == at


def test_expired_limit_cannot_reactivate_after_unobserved_gap():
    times = pd.to_datetime(["2024-01-02T00:00:00Z", "2024-01-02T00:20:00Z"])
    market = bars([[100, 100, 100, 100], [100, 100, 100, 100]], times)
    cfg = PortfolioSettings({"a": 1}, max_open_positions=1, max_total_ounces=1)
    result = run_limit_portfolio(market, [order(times[0] + pd.Timedelta(seconds=30),
                                                    "a", 1, 100, 99, 101, expiry=1)], cfg)
    assert result.trades.empty
    assert result.expired_signals == 1


def test_invalid_m1_time_axis_rejected():
    market = bars([[100, 100, 100, 100]])
    market.index = market.index + pd.Timedelta(seconds=1)
    cfg = PortfolioSettings({"a": 1})
    with pytest.raises(ValueError, match="minute opens"):
        run_limit_portfolio(market, [], cfg)


def test_seeded_limit_streams_preserve_shared_ledger():
    for seed in range(12):
        rng = np.random.default_rng(seed)
        idx = pd.date_range("2024-01-02T00:00:00Z", periods=160, freq="min")
        mid = 100 + np.cumsum(rng.normal(0, .12, len(idx)))
        market = bars(np.column_stack([mid, mid + .3, mid - .3, mid]), idx)
        cfg = PortfolioSettings({"a": 1, "b": 1}, max_open_positions=2, max_total_ounces=2)
        orders = []
        for n in range(1, 25):
            side = 1 if n % 2 else -1
            price = float(mid[n * 5])
            orders.append(order(idx[n * 5], "a" if n % 3 else "b", side,
                                price, price - side * .25, price + side * .4, expiry=3))
        result = run_limit_portfolio(market, orders, cfg)
        assert validate_portfolio(result, cfg)["status"] == "PASSED"
        assert result.trades["cost"].sum() == pytest.approx(.4 * result.trades["ounces"].sum())
        assert result.equity["open_positions"].max() <= 2


def test_unconstrained_shared_limit_matches_two_independent_reference_runs():
    from norisk_quant.limit_engine import run_limits
    from norisk_quant.model import Settings

    market = bars([
        [100, 100, 100, 100],
        [100, 102, 99.5, 100.5],
        [100.5, 101.2, 99.6, 100.8],
        [100.8, 101.5, 99.2, 100],
        [100, 100.2, 99.8, 100],
    ])
    at = market.index[1]
    buy = order(at, "a", 1, 100, 99, 101)
    sell = order(at, "b", -1, 100, 101.5, 99)
    cfg = PortfolioSettings({"a": 1, "b": 1}, max_open_positions=2, max_total_ounces=2)
    shared = run_limit_portfolio(market, [buy, sell], cfg)
    a = run_limits(market, [buy], Settings())
    b = run_limits(market, [sell], Settings())
    for name, standalone in (("a", a), ("b", b)):
        pd.testing.assert_frame_equal(
            shared.trades.loc[shared.trades["strategy"] == name].reset_index(drop=True),
            standalone.trades.reset_index(drop=True), check_dtype=False,
        )
    np.testing.assert_allclose(
        shared.equity["equity"].to_numpy(),
        (a.equity["equity"] + b.equity["equity"]).to_numpy(), rtol=0, atol=1e-7,
    )
