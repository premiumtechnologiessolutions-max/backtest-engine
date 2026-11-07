"""Synthetic fail-closed checks: FAC025 source-only spread stress, no trades."""
from datetime import datetime, timezone

import pytest

from scripts.research_fac025_entry_spread_stress import (
    NY, candidate_entry_open_spreads, _percentile_nearest_rank,
)


def fixture_rows():
    start = 1_700_000_000 // 900 * 900
    rows = []
    for quarter in range(48):
        base = 100 + (quarter // 4) * 0.01
        for minute in range(15):
            price = base
            low, close = price, price
            if quarter == 40 and minute == 14:
                # Prior four M15 lows are >=100.09. Sweep and reclaim.
                low, close = 100.08, 100.10
            high = max(price, close)
            ts = start + quarter * 900 + minute * 60
            spread = 0.50 if quarter == 41 and minute == 2 else 0.30
            rows.append({"ts": ts, "o": price, "h": high, "l": low, "c": close,
                         "ao": price + spread, "ah": high + spread,
                         "al": low + spread, "ac": close + spread})
    return rows


def test_structural_source_does_not_claim_execution():
    result = candidate_entry_open_spreads(fixture_rows())
    assert result["counts"]["normalized_risk_candidates"] >= 1
    assert result["counts"]["observed_next_open_candidates"] >= 1
    assert sum(x["observed_candidate_opens"] for x in
               (m["ALL"] for m in result["months"].values())) == result["counts"]["ALL"]
    assert sum(x["spread_gt_fixed_fee_count"] for x in
               (m["ALL"] for m in result["months"].values())) >= 1


def test_missing_next_open_is_never_interpolated():
    rows = fixture_rows()
    original = candidate_entry_open_spreads(rows)
    missing = rows[40 * 15 + 17]["ts"]
    filtered = [row for row in rows if row["ts"] != missing]
    result = candidate_entry_open_spreads(filtered)
    assert result["counts"].get("observed_next_open_candidates", 0) < original["counts"]["observed_next_open_candidates"]


@pytest.mark.parametrize("field,value", [
    ("ts", True), ("o", "100"), ("ao", float("nan")),
    ("h", -1), ("ao", 0), ("al", -1),
])
def test_rejects_malformed_quote_rows(field, value):
    rows = fixture_rows()
    rows[0][field] = value
    with pytest.raises(ValueError):
        candidate_entry_open_spreads(rows)


def test_rejects_crossed_and_duplicate_quotes():
    rows = fixture_rows()
    for key in ("ao", "ah", "al", "ac"):
        rows[0][key] = rows[0][key[1:]] - 0.01
    with pytest.raises(ValueError, match="Crossed"):
        candidate_entry_open_spreads(rows)
    rows = fixture_rows()
    rows[1]["ts"] = rows[0]["ts"]
    with pytest.raises(ValueError, match="duplicate"):
        candidate_entry_open_spreads(rows)


def test_nearest_rank_small_sample_and_floating_fee_boundary():
    assert _percentile_nearest_rank([0.1, 0.2, 0.3], 95) == 0.3
    assert _percentile_nearest_rank([0.1, 0.2, 0.3], 50) == 0.2
    with pytest.raises(ValueError):
        _percentile_nearest_rank([], 95)
    assert not (0.400000000000005 > 0.40 + 1e-9)


def test_new_york_dst_clock_changes_at_correct_utc_hour():
    before = datetime(2026, 3, 7, 14, tzinfo=timezone.utc).astimezone(NY)
    after = datetime(2026, 3, 8, 13, tzinfo=timezone.utc).astimezone(NY)
    assert before.hour == after.hour == 9
    assert before.utcoffset().total_seconds() == -5 * 3600
    assert after.utcoffset().total_seconds() == -4 * 3600
