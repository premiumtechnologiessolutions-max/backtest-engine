"""Synthetic FAC025 monthly M1 risk regressions; no original-source P/L."""
import pandas as pd
import pytest
from scripts.research_fac025_monthly_m1_risk import monthly_observed_m1_risk


def fixture(times, equity, floating=None):
    idx = pd.to_datetime(times, utc=True)
    floating = floating if floating is not None else [0] * len(equity)
    observed = pd.DataFrame({"o": [100] * len(times)}, index=idx)
    marks = pd.DataFrame({"equity": equity,
                          "realized_pnl": [x-y for x,y in zip(equity, floating)],
                          "floating_pnl": floating}, index=idx)
    return observed, marks


def test_cross_month_previous_close_anchor_and_local_peak_reset():
    m, e = fixture(["2026-01-30T23:58Z", "2026-01-30T23:59Z",
                    "2026-02-02T00:00Z", "2026-02-02T00:01Z"],
                   [5, 1, -2, 3], [0, -4, -7, 0])
    rows = monthly_observed_m1_risk(m, e)
    assert [r["month_utc"] for r in rows] == ["2026-01", "2026-02"]
    assert [r["observed_m1_equity_marks"] for r in rows] == [2, 2]
    assert [r["month_local_max_observed_m1_close_drawdown_usd_per_oz"] for r in rows] == [4, 3]


def test_floating_mark_is_included_without_fabricated_gap_minutes():
    m, e = fixture(["2026-01-05T12:00Z", "2026-01-05T12:10Z"], [0, -6], [0, -6])
    assert monthly_observed_m1_risk(m, e)[0]["month_local_max_observed_m1_close_drawdown_usd_per_oz"] == 6


def test_empty_or_mismatched_marks_fail_closed():
    m, e = fixture(["2026-01-05T12:00Z", "2026-01-05T12:01Z"], [0, 1])
    with pytest.raises(ValueError, match="match each observed"):
        monthly_observed_m1_risk(m, e.iloc[:1])
    with pytest.raises(ValueError, match="nonempty"):
        monthly_observed_m1_risk(m.iloc[:0], e.iloc[:0])


@pytest.mark.parametrize("damage", ["duplicate", "unaligned", "naive", "unreconciled", "nan"])
def test_corrupted_source_or_equity_rejected(damage):
    m, e = fixture(["2026-01-05T12:00Z", "2026-01-05T12:01Z"], [0, 1])
    if damage == "duplicate":
        e.index = pd.to_datetime(["2026-01-05T12:00Z"] * 2, utc=True)
    elif damage == "unaligned":
        m.index = pd.to_datetime(["2026-01-05T12:00:01Z", "2026-01-05T12:01:01Z"], utc=True)
        e.index = m.index
    elif damage == "naive":
        m.index = m.index.tz_localize(None)
    elif damage == "unreconciled":
        e.loc[e.index[-1], "realized_pnl"] = 5
    elif damage == "nan":
        e.loc[e.index[-1], "equity"] = float("nan")
    with pytest.raises(ValueError):
        monthly_observed_m1_risk(m, e)


def test_bid_reference_summary_attaches_month_risk_without_inventing_marks():
    from datetime import datetime, timedelta, timezone
    from scripts.research_fac025_canonical_replay import replay_frozen_intents_bid_reference
    from scripts.research_fac025_frozen_entry_policy import POLICY_SHA256
    from scripts.research_fac025_frozen_grid import frozen_specs
    at = datetime(2026, 1, 5, 14, 15, tzinfo=timezone.utc)
    spec = frozen_specs()[0]
    intent = {
        "status": "RESEARCH_INTENT_ONLY", "frozen_entry_policy": "FAC025-ENTRY-A",
        "policy_sha256": POLICY_SHA256,
        "execution": "RESEARCH_INTENT_ONLY_NO_FILLS_NO_ORDERS",
        "max_entry_delay_seconds": 60, "shared_capacity_slots": 1,
        "risk_sizing": "UNDEFINED_NO_POSITION_SIZE",
        "entry_price": "N/A", "stop_price": "N/A", "target_price": "N/A",
        "filter_spec_id": spec["id"], "filter_fingerprint": spec["fingerprint"],
        "side": "BUY", "signal_at": at.isoformat(),
        "entry_deadline_utc": (at + timedelta(minutes=1)).isoformat(),
        "risk_distance_usd_per_oz": 1.0, "target_distance_usd_per_oz": 1.5,
        "fee_usd_per_oz_all_in_roundtrip": .4,
    }
    idx = pd.to_datetime(["2026-01-05T14:15Z", "2026-01-05T14:16Z",
                          "2026-01-05T14:17Z", "2026-02-02T14:15Z"], utc=True)
    m1 = pd.DataFrame([{"o":100, "h":100, "l":100, "c":100},
                       {"o":100, "h":102, "l":98, "c":100},
                       {"o":100, "h":100, "l":100, "c":100},
                       {"o":100, "h":100, "l":100, "c":100}], index=idx)
    _, report = replay_frozen_intents_bid_reference(m1, [intent])
    months = report["monthly_utc_exit_net_usd_per_oz"]
    assert [x["observed_m1_equity_marks"] for x in months] == [3, 1]
    assert [x["month_local_max_observed_m1_close_drawdown_usd_per_oz"] for x in months] == pytest.approx([1.4, 0])
    assert [x["net_usd_per_oz"] for x in months] == pytest.approx([-1.4, 0])
    assert report["monthly_m1_risk_scope"] == "BID_REFERENCE_OBSERVED_CLOSE_MARKS_NOT_INTRABAR_OR_AUTHENTICATED_BIDASK"
