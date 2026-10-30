"""Synthetic guards for FAC026 original-source structural scanner.

No private quotes are checked into the repository or used by these tests.
"""
import json
import zipfile

import pandas as pd
import pytest

from scripts.research_fac026_original_source_structural import (
    candles, load_year, parity_for_variant, run, signals,
)


def sample(minutes=60):
    times = pd.date_range("2012-05-01 12:00", periods=minutes,
                          freq="min", tz="UTC")
    return pd.DataFrame({
        "ts": times.astype("int64") // 10**9,
        "o": [100.0] * minutes, "h": [100.2] * minutes,
        "l": [99.8] * minutes, "c": [100.0] * minutes,
        "ao": [100.4] * minutes, "ah": [100.6] * minutes,
        "al": [100.2] * minutes, "ac": [100.4] * minutes,
    }, index=times)


def test_complete_m15_h1_require_all_observed_minutes():
    df = sample()
    assert candles(df, "15min", 15).full.all()
    assert candles(df, "1h", 60).full.all()
    missing = df.drop(df.index[7])
    assert not candles(missing, "15min", 15).full.all()
    assert not candles(missing, "1h", 60).full.all()


def test_flat_market_never_fabricates_breakout():
    raw, next_opens = signals(sample(600), 8, 0.8, 0.35, (8, 12))
    assert len(raw) == len(next_opens) == 0


def test_source_sha_fails_closed_before_opening_archive(tmp_path):
    path = tmp_path / "fake.zip"
    path.write_bytes(b"not the original")
    with pytest.raises(ValueError, match="SHA mismatch"):
        run(path)


@pytest.mark.parametrize("years", [
    (), (2017,), (2012, 2012), (2013, 2014),
])
def test_only_unique_preregistered_exposed_years(years):
    with pytest.raises(ValueError, match="preregistered"):
        run("nonexistent.zip", years=years)


def test_bad_bid_ask_order_rejected(tmp_path):
    path = tmp_path / "sample.zip"
    row = {"ts": 1325545200, "o": 100, "h": 101, "l": 99,
           "c": 100, "ao": 99, "ah": 102, "al": 100, "ac": 101}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("2012.json", json.dumps([row]))
    with zipfile.ZipFile(path) as archive:
        with pytest.raises(ValueError, match="BID/ASK"):
            load_year(archive, 2012)


def test_positive_causal_m15_h1_signal_and_missing_minute_gate():
    """One complete compressed breakout with real next open; missing data blocks."""
    start = pd.Timestamp("2012-05-01 09:00:00", tz="UTC")
    rows = []
    for i in range(17):
        if i < 8:
            opening = 100 + i * .2
            closing, high, low = opening + .2, opening + 1.2, opening - .8
        elif i < 16:
            opening = 101.6 + (i - 8) * .07
            closing, high, low = opening + .07, opening + .28, opening - .12
        else:
            opening, closing, high, low = 102.38, 102.52, 102.53, 102.38
        for minute in range(15):
            price = opening + (closing - opening) * minute / 14
            top = max(price, high if minute == 0 else price)
            bottom = min(price, low if minute == 0 else price)
            close = closing if minute == 14 else price
            rows.append({
                "ts": int((start + pd.Timedelta(minutes=i * 15 + minute)).timestamp()),
                "o": price, "h": top, "l": bottom, "c": close,
                "ao": price + .3, "ah": top + .3,
                "al": bottom + .3, "ac": close + .3,
            })
    for minute in (255, 256, 257):
        rows.append({
            "ts": int((start + pd.Timedelta(minutes=minute)).timestamp()),
            "o": 102.52, "h": 102.53, "l": 102.51, "c": 102.52,
            "ao": 102.82, "ah": 102.83, "al": 102.81, "ac": 102.82,
        })
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.ts, unit="s", utc=True)
    triggers, eligible = signals(df, 8, .8, .35, (9, 13))
    assert len(triggers) == len(eligible) == 1
    assert parity_for_variant(df, 8, .8, .35, (9, 13))["positive_checks"] == 1
    assert triggers[0] == pd.Timestamp("2012-05-01 13:15:00", tz="UTC")
    assert len(signals(df.drop(df.index[40]), 8, .8, .35, (9, 13))[0]) == 0
    assert len(signals(df.drop(df.index[-1]), 8, .8, .35, (9, 13))[1]) == 0


def test_flat_market_independent_negative_parity():
    result = parity_for_variant(sample(600), 8, .8, .35, (8, 12),
                                negative_per_month=4)
    assert result["positive_checks"] == 0
    assert result["sampled_negative_checks"] > 0
    assert result["executed_trades"] == 0


def test_fabricated_scanner_positive_rejected(monkeypatch):
    from scripts import research_fac026_original_source_structural as scan
    fake = pd.DatetimeIndex([pd.Timestamp("2012-05-01 16:15", tz="UTC")])
    monkeypatch.setattr(scan, "signals", lambda *args: (fake, fake))
    with pytest.raises(ValueError, match="signal mismatch"):
        scan.parity_for_variant(sample(600), 8, .8, .35, (9, 13))


@pytest.mark.parametrize("budget", [0, 65, True])
def test_parity_sample_budget_fails_closed(budget):
    with pytest.raises(ValueError, match="sample budget"):
        parity_for_variant(sample(600), 8, .8, .35, (9, 13),
                           negative_per_month=budget)
