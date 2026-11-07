"""Synthetic source-calendar gap accounting; no private XAUUSD quotes."""
import pandas as pd
import pytest

from norisk_quant.source_gap_integrity import verify_source_gap_minutes as verify


def sample():
    index = pd.to_datetime([
        "2024-01-02T00:00:00Z",
        "2024-01-02T00:03:00Z",
        "2024-01-02T00:07:00Z",
    ])
    return pd.DataFrame(index=index)


def trade(m1, entry=0, close=2, gap=5):
    return pd.DataFrame([{
        "entry_at": m1.index[entry], "closed_at": m1.index[close],
        "gap_minutes": gap,
    }])


def test_multiple_gaps_reconcile_exactly():
    m1 = sample()
    assert verify(m1, trade(m1, gap=5)) == 1
    assert verify(m1, trade(m1, entry=1, gap=3)) == 1


def test_gap_before_entry_is_not_counted():
    m1 = sample()
    assert verify(m1, trade(m1, entry=2, close=2, gap=0)) == 1


def test_contiguous_source_has_zero_missing_minutes():
    index = pd.date_range("2024-01-02", periods=4, freq="min", tz="UTC")
    m1 = pd.DataFrame(index=index)
    assert verify(m1, trade(m1, entry=0, close=3, gap=0)) == 1


@pytest.mark.parametrize("wrong", [0, 2, 4, 6])
def test_fabricated_gap_minutes_are_rejected(wrong):
    m1 = sample()
    with pytest.raises(AssertionError, match="differs from source M1"):
        verify(m1, trade(m1, gap=wrong))


@pytest.mark.parametrize("bad", [True, False, 5.0, "5", -1, None])
def test_gap_schema_rejects_boolean_float_text_negative_and_missing(bad):
    m1 = sample()
    t = trade(m1)
    t["gap_minutes"] = pd.Series([bad], dtype=object)
    with pytest.raises(ValueError, match="nonnegative integer"):
        verify(m1, t)


def test_empty_ledger_is_valid_with_required_columns():
    m1 = sample()
    assert verify(m1, trade(m1).iloc[:0]) == 0


def test_missing_trade_column_is_rejected_even_for_empty_ledger():
    m1 = sample()
    with pytest.raises(ValueError, match="missing trade fields"):
        verify(m1, pd.DataFrame(columns=["entry_at", "closed_at"]))


def test_duplicate_trade_columns_fail_closed():
    m1 = sample()
    t = trade(m1)
    t["copy"] = t["gap_minutes"]
    t.columns = [*t.columns[:-1], "gap_minutes"]
    with pytest.raises(ValueError, match="unique columns"):
        verify(m1, t)


def test_reversed_or_absent_source_trade_time_fails_closed():
    m1 = sample()
    with pytest.raises(AssertionError, match="absent or reversed"):
        verify(m1, trade(m1, entry=2, close=0, gap=0))
    t = trade(m1)
    t.loc[0, "closed_at"] = pd.Timestamp("2024-01-02T00:06:00Z")
    with pytest.raises(AssertionError, match="absent or reversed"):
        verify(m1, t)


def test_naive_trade_timestamp_fails_closed():
    m1 = sample()
    t = trade(m1)
    t["entry_at"] = pd.Series([pd.Timestamp("2024-01-02T00:00:00")], dtype=object)
    with pytest.raises(ValueError, match="UTC-aware entry_at"):
        verify(m1, t)


def test_duplicate_or_non_utc_or_off_minute_source_fails_closed():
    m1 = sample()
    duplicate = pd.concat([m1, m1.iloc[:1]])
    with pytest.raises(ValueError, match="sorted unique UTC"):
        verify(duplicate, trade(m1))
    local = m1.copy()
    local.index = local.index.tz_convert("Europe/Paris")
    with pytest.raises(ValueError, match="sorted unique UTC"):
        verify(local, trade(m1))
    shifted = m1.copy()
    shifted.index = shifted.index + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="minute-aligned"):
        verify(shifted, trade(m1))


def test_real_limit_executor_gap_stop_ledger_reconciles():
    from norisk_quant.limit_engine import LimitOrder, run_limits
    from norisk_quant.model import Settings

    m1 = sample().iloc[:2].copy()
    m1["o"] = [100., 94.]
    m1["h"] = [101., 100.]
    m1["l"] = [99., 93.]
    m1["c"] = [100., 94.]
    order = LimitOrder(
        placed_at=m1.index[0], expires_at=m1.index[1],
        side=1, price=100., stop=95., target=110.,
    )
    result = run_limits(
        m1, [order],
        Settings(ounces=1.0, roundtrip_cost_per_ounce=.40, close_at_end=True),
    )
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["exit_reason"] == "gap_stop"
    assert result.trades.iloc[0]["gap_minutes"] == 2
    assert verify(m1, result.trades) == 1


def test_frozen_runner_blocks_falsified_gap_count_before_report(tmp_path, monkeypatch):
    """Integration: accounting cannot certify a false M1 missing-minute count."""
    from types import SimpleNamespace
    import scripts.run_bos_fib_frozen_sensitivity as frozen
    from norisk_quant.source_bar_exit_integrity import AUDITED_REASONS

    source = tmp_path / "SYNTHETIC_NOT_REAL_GOLD.zip"
    source.write_bytes(b"synthetic source only")
    monkeypatch.setattr(frozen, "sha256_file", lambda _: frozen.SOURCE_SHA)
    index = pd.date_range("2012-01-01", periods=12, freq="MS", tz="UTC")
    quotes = pd.DataFrame({"o": [100.] * 12}, index=index)
    monkeypatch.setattr(frozen, "load_market", lambda *a, **k: quotes)
    monkeypatch.setattr(frozen, "bos_fib_limit_orders", lambda *a, **k: [])
    monkeypatch.setattr(frozen, "filter_orders_h1", lambda *a, **k: [])
    fake_trade = pd.DataFrame([{
        "entry_at": index[0], "closed_at": index[1],
        "gap_minutes": 0, "exit_reason": "target",
    }])
    monkeypatch.setattr(
        frozen, "run_limits", lambda *a, **k: SimpleNamespace(trades=fake_trade)
    )
    monkeypatch.setattr(frozen, "verify_source_open_exit_prices", lambda *a: 0)
    monkeypatch.setattr(
        frozen, "verify_source_bar_exit_prices",
        lambda *a: {reason: int(reason == "target") for reason in AUDITED_REASONS},
    )
    monkeypatch.setattr(
        frozen, "report",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("Unverified gap ledger must not reach report")
        ),
    )
    output = tmp_path / "out"
    with pytest.raises(AssertionError, match="differs from source M1"):
        frozen.execute(source, [2012], output)
    assert not (output / "2012").exists()
    assert not (output / "frozen_sensitivity_summary.json").exists()
