"""Frozen QS01 and elapsed-time execution contracts, using synthetic quotes only."""
import json
import sys
import numpy as np
import pandas as pd
import pytest

from norisk_quant.qs01 import qs01_signals, QS01_STRATEGY
from norisk_quant.model import Settings, Signal
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.quote_stress import STRATEGY, quote_stress_signals, qs01_settings
from norisk_quant import cli
from norisk_quant.accounting import validate_execution
from norisk_quant.report import report


def quotes():
    n = 243
    idx = pd.date_range("2024-01-02T00:00:00Z", periods=n, freq="min")
    c = np.full(n, 100.0)
    c[240:] = 99.3
    o, h, l = c.copy(), c + 0.2, c - 0.2
    s = np.full(n, 0.2)
    s[240] = 0.6
    return pd.DataFrame({
        "o": o, "h": h, "l": l, "c": c,
        "ao": o + s, "ah": h + s, "al": l + s, "ac": c + s,
    }, index=idx)


def test_frozen_spread_shock_uses_only_prior_atr_and_spread():
    data = quotes()
    result = qs01_signals(data)
    assert len(result) == 1
    sig = result[0]
    assert sig.strategy == QS01_STRATEGY
    assert sig.side == 1
    assert sig.confirmed_at == data.index[241]
    assert sig.stop_distance == pytest.approx(0.6)
    assert sig.target_distance == pytest.approx(0.6)
    changed = data.copy()
    changed.loc[changed.index[241]:, ["o", "h", "l", "c", "ao", "ah", "al", "ac"]] = 120
    assert qs01_signals(changed)[0] == sig


def test_incomplete_prior_240_minute_window_rejected():
    data = quotes()
    assert qs01_signals(data.drop(index=data.index[200])) == []


def test_no_shock_no_signal_and_crossed_quotes_fail_closed():
    data = quotes()
    data.loc[data.index[240], ["ao", "ah", "al", "ac"]] -= 0.4
    assert qs01_signals(data) == []
    data.loc[data.index[240], "ac"] = data.loc[data.index[240], "c"] - 0.1
    with pytest.raises(ValueError, match="crossed"):
        qs01_signals(data)


def market(rows, timestamps):
    return pd.DataFrame(rows, columns=["o", "h", "l", "c"],
                        index=pd.to_datetime(timestamps, utc=True))


def replay_both(bars, signals, cfg):
    a = run(bars, signals, cfg)
    b = run_fast(bars, signals, cfg)
    pd.testing.assert_frame_equal(a.trades, b.trades, check_dtype=False)
    pd.testing.assert_frame_equal(a.equity, b.equity, check_dtype=False)
    assert a.expired_signals == b.expired_signals
    assert a.pending_at_end == b.pending_at_end
    return a


def test_time_exit_after_30_elapsed_utc_minutes_carries_gap(tmp_path):
    bars = market([
        [100, 100, 100, 100], [100, 100, 100, 100],
        [100, 100, 100, 100], [102, 102, 102, 102],
        [102, 102, 102, 102],
    ], [
        "2024-01-02T00:00:00Z", "2024-01-02T00:01:00Z",
        "2024-01-02T00:02:00Z", "2024-01-02T00:31:00Z",
        "2024-01-02T00:32:00Z",
    ])
    sig = Signal(bars.index[1], 1, 5, 5, "QS01")
    cfg = Settings(max_entry_delay_minutes=0, max_hold_minutes=30)
    result = replay_both(bars, [sig], cfg)
    assert len(result.trades) == 1
    row = result.trades.iloc[0]
    assert row["exit_reason"] == "time_exit"
    assert row["closed_at"] == bars.index[3]
    assert row["gap_minutes"] == 28
    assert row["net_pnl"] == pytest.approx(1.6)
    assert validate_execution(result, cfg)["accounting_checks"] == "PASSED"
    assert report(result, cfg, tmp_path)["net_pnl"] == pytest.approx(1.6)


def test_gap_stop_has_priority_over_time_exit():
    bars = market([
        [100, 100, 100, 100], [100, 100, 100, 100],
        [90, 90, 90, 90],
    ], ["2024-01-02T00:00:00Z", "2024-01-02T00:01:00Z",
        "2024-01-02T00:31:00Z"])
    result = replay_both(
        bars, [Signal(bars.index[1], 1, 5, 5, "QS01")],
        Settings(max_entry_delay_minutes=0, max_hold_minutes=30),
    )
    assert result.trades.iloc[0]["exit_reason"] == "gap_stop"
    assert result.trades.iloc[0]["exit_price"] == 90
    assert result.trades.iloc[0]["net_pnl"] == pytest.approx(-10.4)


def test_next_observed_open_after_missing_next_minute_is_not_entry():
    bars = market([
        [100, 100, 100, 100], [100, 100, 100, 100],
    ], ["2024-01-02T00:00:00Z", "2024-01-02T00:10:00Z"])
    result = replay_both(
        bars, [Signal(pd.Timestamp("2024-01-02T00:01:00Z"), 1, 5, 5, "QS01")],
        Settings(max_entry_delay_minutes=0, max_hold_minutes=30),
    )
    assert result.trades.empty
    assert result.expired_signals == 1


def test_time_exit_opt_in_only_and_reject_invalid_holds():
    bars = market([
        [100, 100, 100, 100], [100, 100, 100, 100],
        [100, 100, 100, 100],
    ], ["2024-01-02T00:00:00Z", "2024-01-02T00:01:00Z",
        "2024-01-02T00:32:00Z"])
    assert Settings(1, 0.40, 1, True).max_hold_minutes is None
    result = replay_both(bars, [Signal(bars.index[1], 1, 5, 5, "baseline")], Settings())
    assert result.trades.iloc[0]["exit_reason"] == "end_of_data"
    for bad in (0, -1, 1.5, True):
        with pytest.raises(ValueError, match="max hold"):
            Settings(max_hold_minutes=bad)


def test_public_qs01_wrapper_uses_canonical_audited_signals():
    data = quotes()
    assert QS01_STRATEGY == STRATEGY
    assert qs01_signals(data) == quote_stress_signals(data)
    assert qs01_signals(data.iloc[:241]) == quote_stress_signals(data.iloc[:241])


@pytest.mark.parametrize("missing", ["o", "h", "l", "c", "ao", "ah", "al", "ac"])
def test_public_qs01_wrapper_requires_all_original_quote_columns(missing):
    with pytest.raises(ValueError, match="original Bid/Ask"):
        qs01_signals(quotes().drop(columns=[missing]))


@pytest.mark.parametrize("column,value", [("ac", np.nan), ("ao", np.inf), ("al", -1), ("ah", 1)])
def test_public_qs01_wrapper_preserves_strict_quote_guards(column, value):
    data = quotes()
    data.loc[data.index[0], column] = value
    with pytest.raises(ValueError, match="finite|invalid"):
        qs01_signals(data)


@pytest.mark.parametrize("execution", ["reference", "fast"])
def test_cli_qs01_executes_canonical_rules_settings_and_time_exit(tmp_path, monkeypatch, capsys, execution):
    data = quotes()
    tail_index = pd.date_range(data.index[-1] + pd.Timedelta(minutes=1), periods=40, freq="min")
    tail = pd.DataFrame(np.repeat(data.iloc[-1:].to_numpy(), len(tail_index), axis=0), index=tail_index, columns=data.columns)
    data = pd.concat([data, tail])
    monkeypatch.setattr(cli, "load_market", lambda *_: data)
    monkeypatch.setattr(sys, "argv", [
        "norisk", "backtest", "--strategy", "qs01", "--timeframe", "M1",
        "--execution", execution, "--data", str(tmp_path / "synthetic.json"),
        "--start", "2024-01-02", "--end", "2024-01-02", "--out", str(tmp_path / "report"),
    ])
    cli.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["settings"]["max_holding_minutes"] == 30
    assert summary["settings"]["max_entry_delay_minutes"] == 0
    assert summary["settings"]["ounces"] == 1
    assert summary["total_fees"] == .4
    expected = run(data, quote_stress_signals(data), qs01_settings())
    assert expected.trades.iloc[0]["exit_reason"] == "time_exit"
    observed = pd.read_csv(tmp_path / "report" / "trades.csv", parse_dates=["entry_at", "closed_at", "signal_at"])
    pd.testing.assert_frame_equal(observed.loc[:, expected.trades.columns], expected.trades, check_dtype=False)


@pytest.mark.parametrize("extra", [["--timeframe", "M15"], ["--ounces", "2"]])
def test_cli_qs01_rejects_nonfrozen_arguments_before_data_load(tmp_path, monkeypatch, extra):
    def unexpected_load(*_):
        pytest.fail("Nonfrozen QS01 must fail before loading any data")
    monkeypatch.setattr(cli, "load_market", unexpected_load)
    monkeypatch.setattr(sys, "argv", [
        "norisk", "backtest", "--strategy", "qs01", "--timeframe", "M1",
        "--data", str(tmp_path / "missing.json"), "--start", "2024-01-02",
        "--end", "2024-01-02", "--out", str(tmp_path / "report"), *extra,
    ])
    with pytest.raises(SystemExit, match="2"):
        cli.main()
