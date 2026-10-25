import math

import pandas as pd
import pytest

from norisk_quant.bos_fib import BosFibSettings, bos_fib_limit_orders


def choppy_synthetic(n=320):
    dates = pd.date_range("2024-01-02T00:00:00Z", periods=n, freq="min")
    prices = [100 + 0.075 * i + 1.7 * math.sin(i * 0.26) for i in range(n)]
    return pd.DataFrame(
        {
            "o": prices,
            "h": [p + 0.14 for p in prices],
            "l": [p - 0.14 for p in prices],
            "c": prices,
        },
        index=dates,
    )


def test_causal_no_future_data_in_signals():
    frame = choppy_synthetic()
    cfg = BosFibSettings()
    full = bos_fib_limit_orders(frame, settings=cfg)
    assert full
    first = full[0]
    cutoff = first.placed_at
    prefix = frame.loc[frame.index < cutoff]
    prefix_orders = bos_fib_limit_orders(prefix, settings=cfg)
    assert prefix_orders
    assert prefix_orders[0] == first
    changed = frame.copy()
    changed.loc[changed.index >= cutoff, ["o", "h", "l", "c"]] = [200, 201, 199, 200]
    changed_orders = bos_fib_limit_orders(changed, settings=cfg)
    assert [o for o in changed_orders if o.placed_at <= cutoff] == [
        o for o in full if o.placed_at <= cutoff
    ]


def test_order_risk_and_fib_params_are_respected():
    frame = choppy_synthetic()
    base = bos_fib_limit_orders(frame, settings=BosFibSettings())
    deeper = bos_fib_limit_orders(frame, settings=BosFibSettings(fib_entry=0.705))
    wider = bos_fib_limit_orders(frame, settings=BosFibSettings(reward_risk=1.5))
    assert base and len(base) == len(deeper) == len(wider)
    for a, b, c in zip(base, deeper, wider):
        assert a.placed_at == b.placed_at == c.placed_at
        assert a.stop == pytest.approx(b.stop)
        assert abs(b.price - b.stop) < abs(a.price - a.stop)
        assert abs(c.target - c.price) == pytest.approx(1.5 * abs(c.price - c.stop))
        assert abs(a.target - a.price) == pytest.approx(abs(a.price - a.stop))


def test_gap_inside_impulse_not_used_as_complete_structure():
    frame = choppy_synthetic()
    original = bos_fib_limit_orders(frame)
    assert original
    target = original[0]
    frame = frame.drop(
        frame.index[
            (frame.index >= target.placed_at - pd.Timedelta(minutes=6))
            & (frame.index < target.placed_at)
        ]
    )
    assert target not in bos_fib_limit_orders(frame)


def test_only_first_two_bos_waves_per_structure_regime():
    frame = choppy_synthetic()
    limited = bos_fib_limit_orders(
        frame, settings=BosFibSettings(max_bos_waves_per_regime=1)
    )
    baseline = bos_fib_limit_orders(
        frame, settings=BosFibSettings(max_bos_waves_per_regime=2)
    )
    assert len(limited) <= len(baseline)
    assert all("wave1_" in o.strategy for o in limited)
    assert all(any(f"wave{i}_" in o.strategy for i in (1, 2)) for o in baseline)


def test_invalid_settings_or_bars_rejected():
    with pytest.raises(ValueError):
        BosFibSettings(fib_entry=0.9)
    with pytest.raises(ValueError):
        BosFibSettings(reward_risk=0)
    frame = choppy_synthetic()
    frame.iloc[0, frame.columns.get_loc("h")] = 0
    with pytest.raises(ValueError, match="Invalid OHLC"):
        bos_fib_limit_orders(frame)
