"""Adversarial point-in-time event revision tests; no market or OOS data."""
import pandas as pd
import pytest

from norisk_quant.causal_market_context import (
    Observation, ScheduledEvent, as_of, news_blackout, schedules_from_json,
)


def observation(value, release, seen, vintage):
    return Observation("US_POLICY", "policy_rate", value, pd.Timestamp(release),
                       pd.Timestamp(seen), vintage, "PUBLIC_FEED")


def event(announced, scheduled, impact="high", cancelled=False):
    return ScheduledEvent("US_CPI_RELEASE", "USD", pd.Timestamp(announced),
                          pd.Timestamp(scheduled), impact, "PUBLIC_FEED",
                          cancelled=cancelled)


def test_late_old_macro_backfill_does_not_override_newer_release():
    old = observation(5.0, "2026-10-01T12:00:00Z", "2026-11-03T12:00:00Z", "old")
    current = observation(4.0, "2026-11-02T12:00:00Z", "2026-11-02T12:01:00Z", "new")
    assert as_of((old, current), "2026-11-03T13:00:00Z")["US_POLICY"] == current
    assert as_of((current, old), "2026-11-03T13:00:00Z")["US_POLICY"] == current


def test_revisions_of_same_release_only_apply_after_seen_time():
    first = observation(4.0, "2026-11-02T12:00:00Z", "2026-11-02T12:01:00Z", "first")
    corrected = observation(4.2, "2026-11-02T12:00:00Z", "2026-11-03T12:00:00Z", "second")
    assert as_of((first, corrected), "2026-11-02T13:00:00Z")["US_POLICY"] == first
    assert as_of((corrected, first), "2026-11-03T13:00:00Z")["US_POLICY"] == corrected


def test_identical_macro_clocks_with_conflicting_values_fail_closed():
    a = observation(4.0, "2026-11-02T12:00:00Z", "2026-11-02T12:01:00Z", "first")
    b = observation(4.2, "2026-11-02T12:00:00Z", "2026-11-02T12:01:00Z", "second")
    with pytest.raises(ValueError, match="Contradictory macro"):
        as_of((a, b), "2026-11-03T12:00:00Z")


def test_news_reschedule_replaces_old_blackout_without_future_leakage():
    old = event("2026-11-01T10:00:00Z", "2026-11-03T13:30:00Z")
    new = event("2026-11-02T10:00:00Z", "2026-11-03T15:30:00Z")
    assert news_blackout((old, new), "XAU_USD", "2026-11-03T13:30:00Z") == ()
    assert news_blackout((new, old), "XAU_USD", "2026-11-03T15:30:00Z") == ("US_CPI_RELEASE",)
    assert news_blackout((old, new), "XAU_USD", "2026-11-01T13:30:00Z") == ()


def test_news_downgrade_and_cancellation_supersede_old_high_impact():
    high = event("2026-11-01T10:00:00Z", "2026-11-03T13:30:00Z")
    low = event("2026-11-02T10:00:00Z", "2026-11-03T13:30:00Z", "low")
    cancelled = event("2026-11-02T11:00:00Z", "2026-11-03T13:30:00Z", cancelled=True)
    assert news_blackout((high, low), "XAU_USD", "2026-11-03T13:30:00Z") == ()
    assert news_blackout((high, cancelled), "XAU_USD", "2026-11-03T13:30:00Z") == ()


def test_equal_news_revision_clock_must_not_use_input_order():
    high = event("2026-11-01T10:00:00Z", "2026-11-03T13:30:00Z")
    low = event("2026-11-01T10:00:00Z", "2026-11-03T13:30:00Z", "low")
    with pytest.raises(ValueError, match="Conflicting news"):
        news_blackout((high, low), "XAU_USD", "2026-11-03T13:30:00Z")


def test_old_json_schedules_remain_compatible_and_new_cancelled_is_typed():
    raw = {"event_id": "US_CPI_RELEASE", "currency": "USD",
           "announced_at": "2026-11-01T10:00:00Z",
           "scheduled_at": "2026-11-03T13:30:00Z",
           "impact": "high", "source": "PUBLIC_FEED"}
    assert schedules_from_json([raw])[0].cancelled is False
    assert schedules_from_json([{**raw, "cancelled": True}])[0].cancelled is True
    with pytest.raises(ValueError):
        schedules_from_json([{**raw, "cancelled": "false"}])
