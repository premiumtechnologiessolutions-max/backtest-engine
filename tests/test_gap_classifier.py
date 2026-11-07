import pandas as pd
import pytest

from norisk_quant.gaps import classify_gap, classify_index_gaps, holiday_hints


@pytest.mark.parametrize(
    "before,after",
    [
        ("2024-01-10T21:59:00Z", "2024-01-10T23:00:00Z"),  # EST 16:59 to 18:00
        ("2024-07-17T20:59:00Z", "2024-07-17T22:00:00Z"),  # EDT 16:59 to 18:00
    ],
)
def test_daily_rollover_obeys_new_york_dst(before, after):
    row = classify_gap(pd.Timestamp(before), pd.Timestamp(after))
    assert row["missing_minutes"] == 60
    assert row["classification"] == "regular_daily_break_pattern"
    assert row["needs_review"] is False


def test_weekend_pattern_never_proves_broker_schedule():
    row = classify_gap(
        pd.Timestamp("2024-01-05T21:59:00Z"),
        pd.Timestamp("2024-01-07T23:00:00Z"),
    )
    assert row["classification"] == "regular_weekend_pattern"
    assert row["confidence"] == "high_time_match"
    assert row["missing_minutes"] == 2940


def test_good_friday_hint_does_not_assert_verified_market_close():
    row = classify_gap(
        pd.Timestamp("2026-04-02T20:58:00Z"),
        pd.Timestamp("2026-04-05T22:00:00Z"),
    )
    assert row["classification"] == "holiday_calendar_candidate"
    assert row["needs_review"]
    assert "Good Friday" in row["calendar_hints_not_verified"]
    assert pd.Timestamp("2026-04-03").date() in holiday_hints(2026)


def test_unknown_gap_during_active_session_needs_manual_review():
    row = classify_gap(
        pd.Timestamp("2024-07-17T14:00:00Z"),
        pd.Timestamp("2024-07-17T14:15:00Z"),
    )
    assert row["classification"] == "unexplained_active_session"
    assert row["missing_minutes"] == 14
    assert row["needs_review"] is True


def test_gap_index_counts_missing_minutes_and_handles_empty():
    idx = pd.to_datetime(
        [
            "2024-01-10T21:59:00Z", "2024-01-10T23:00:00Z",
            "2024-01-10T23:01:00Z",
        ],
        utc=True,
    )
    rows = classify_index_gaps(idx, min_missing_minutes=10)
    assert len(rows) == 1
    assert int(rows.iloc[0]["missing_minutes"]) == 60
    assert classify_index_gaps(idx, min_missing_minutes=61).empty


def test_duplicate_or_naive_index_fails_closed():
    with pytest.raises(ValueError):
        classify_index_gaps(pd.DatetimeIndex(["2024-01-01", "2024-01-01"]))
    with pytest.raises(ValueError):
        classify_gap(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"))
