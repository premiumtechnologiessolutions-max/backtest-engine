"""Read-only OpenBB research adapter tests; no actual external network."""
import asyncio
from datetime import date
import pandas as pd
import pytest

from norisk_quant.openbb_fred_snapshot import (
    fetch_fred_snapshot, freeze_fred_snapshot, to_prospective_causal_events,
    verify_fred_snapshot,
)
from norisk_quant.causal_stream_merge import merge_causal_streams

STAMP = "2026-11-04T14:00:00+00:00"


def frozen():
    return freeze_fred_snapshot("GDP", "2024-01-01", "2024-12-31",
                                [{"date": "2024-01-01", "GDP": 10.5},
                                 {"date": "2024-04-01", "GDP": 11}],
                                captured_at=STAMP)


class FakeExecutor:
    def __init__(self, rows):
        self.calls, self.rows = [], rows

    async def execute(self, provider, model, params, credentials):
        self.calls.append((provider, model, params, credentials))
        return self.rows


def test_openbb_fredseries_executor_contract():
    executor = FakeExecutor([{"date": date(2024, 1, 1), "GDP": 10.5}])
    captured = asyncio.run(fetch_fred_snapshot(
        "GDP", "2024-01-01", "2024-12-31", executor=executor,
        clock=lambda: pd.Timestamp(STAMP)))
    assert executor.calls[0][0:2] == ("fred", "FredSeries")
    assert executor.calls[0][2]["use_cache"] is False
    assert captured["snapshot_sha256"]
    assert verify_fred_snapshot(captured) == captured
    assert captured["backtest_historical_admissible"] is False


def test_historical_observation_is_not_available_before_capture():
    events = to_prospective_causal_events(frozen())
    assert len(events) == 2
    assert events[0].event_at_ns == pd.Timestamp("2024-01-01T00:00:00Z").value
    assert events[1].event_at_ns == pd.Timestamp("2024-04-01T00:00:00Z").value
    assert all(e.available_at_ns == pd.Timestamp(STAMP).value for e in events)
    assert all(e.available_at_ns > e.event_at_ns for e in events)
    past = pd.Timestamp("2025-01-01T00:00:00Z").value
    assert list(merge_causal_streams({"openbb_fred": events}, through_ns=past)) == []
    assert [e.values[0] for e in merge_causal_streams({"openbb_fred": events})] == [10.5, 11.0]


@pytest.mark.parametrize("field,value", [
    ("backtest_historical_admissible", True), ("historical_release_verified", True),
    ("trade_execution_authorized", True), ("provider_target_commit", "a" * 40)])
def test_no_false_provenance_or_trading_approval(field, value):
    s = frozen()
    s[field] = value
    with pytest.raises(ValueError):
        verify_fred_snapshot(s)


def test_snapshot_content_mutation_refused():
    s = frozen()
    s["rows"][0]["value"] += 1
    with pytest.raises(ValueError, match="digest"):
        verify_fred_snapshot(s)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), None, True, "10"])
def test_invalid_numeric_data_never_silently_zeroed(bad):
    with pytest.raises(ValueError):
        freeze_fred_snapshot("GDP", "2024-01-01", "2024-12-31",
                             [{"date": "2024-01-01", "GDP": bad}], captured_at=STAMP)


@pytest.mark.parametrize("symbol", ["GDP,FRED", "../fred", "", "fred", "GDP "])
def test_only_one_safe_series(symbol):
    with pytest.raises(ValueError):
        freeze_fred_snapshot(symbol, "2024-01-01", "2024-12-31",
                             [{"date": "2024-01-01", "GDP": 10}], captured_at=STAMP)


def test_provider_duplicate_and_unsorted_dates_rejected():
    with pytest.raises(ValueError, match="strictly ordered"):
        freeze_fred_snapshot("GDP", "2024-01-01", "2024-12-31",
                             [{"date": "2024-05-01", "GDP": 10},
                              {"date": "2024-04-01", "GDP": 11}], captured_at=STAMP)


def test_impossible_backdated_capture_rejected():
    with pytest.raises(ValueError, match="Capture cannot predate"):
        freeze_fred_snapshot("GDP", "2024-01-01", "2024-12-31",
                             [{"date": "2024-01-01", "GDP": 1}],
                             captured_at="2024-01-01T00:00:00Z")


def test_invalid_query_never_contacts_provider():
    executor = FakeExecutor([])
    with pytest.raises(ValueError):
        asyncio.run(fetch_fred_snapshot("../", "2024-01-01", "2024-12-31",
                                        executor=executor))
    assert executor.calls == []


def test_provider_error_redacts_secrets():
    class Broken:
        async def execute(self, *a, **kw):
            raise RuntimeError("SECRET_TOKEN_SHOULD_NOT_LEAK")

    with pytest.raises(RuntimeError, match="FRED read-only query failed") as error:
        asyncio.run(fetch_fred_snapshot("GDP", "2024-01-01", "2024-12-31",
                                        executor=Broken()))
    assert "SECRET_TOKEN" not in str(error.value)
