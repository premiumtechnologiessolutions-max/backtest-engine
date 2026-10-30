"""Synthetic-only independent source-vs-canonical FAC025 parity tests."""
from datetime import datetime, timezone

import pytest

from scripts import verify_fac025_source_proxy_parity as parity

BASE = int(datetime(2026, 1, 5, 14, 15, tzinfo=timezone.utc).timestamp())


def bars(prices, offsets=None):
    if offsets is None:
        offsets = range(len(prices))
    return [
        {"ts": BASE + offset * 60, "o": p[0], "h": p[1], "l": p[2], "c": p[3],
         "ao": p[0] + 0.2, "ah": p[1] + 0.2,
         "al": p[2] + 0.2, "ac": p[3] + 0.2}
        for offset, p in zip(offsets, prices)
    ]


def candidate(rows, idx=1, side=1, risk=1.0):
    return {"entry_idx": idx, "entry_at": rows[idx]["ts"],
            "decision": rows[idx]["ts"] - 60,
            "side": side, "risk": risk,
            "ratios": {4: 0.001, 8: 0.001, 12: 0.001},
            "ny_hour": 9, "ny_day": "2026-01-05"}


@pytest.mark.parametrize("prices,offsets,side,risk,expected_net", [
    ([(100, 100, 100, 100), (100, 102, 98, 100)], None, 1, 1, -1.4),
    ([(100, 100, 100, 100), (100, 100.5, 99.8, 100),
      (96, 97, 95, 96)], [0, 1, 5], 1, 1, -4.4),
    ([(100, 100, 100, 100), (100, 100.5, 99.8, 100),
      (103, 104, 102, 103)], [0, 1, 5], 1, 1, 1.1),
    ([(100, 100, 100, 100), (100, 102, 98, 100)], None, -1, 1, -1.4),
    ([(100, 100, 100, 100), (100, 100.2, 99.8, 100),
      (100.2, 100.4, 100.1, 100.3)], None, 1, 5, -0.1),
])
def test_source_selected_trade_matches_both_canonical_engines(
    prices, offsets, side, risk, expected_net
):
    rows = bars(prices, offsets)
    result = parity.verify_rows(rows, [candidate(rows, side=side, risk=risk)])
    assert result["source_selected_trades"] == 1
    assert result["net_usd_per_oz"] == pytest.approx(expected_net)
    assert result["canonical_run_fast_trade_and_m1_parity"] is True
    assert result["source_vs_canonical_trade_and_m1_parity"] is True
    assert result["approved_strategies"] == 0


def test_empty_portfolio_reconciles_zero_month_without_fabrication():
    rows = bars([(100, 100, 100, 100), (100, 100, 100, 100)])
    report = parity.verify_rows(rows, [])
    assert report["source_selected_trades"] == 0
    assert report["net_usd_per_oz"] == 0
    assert report["positive_months"] == 0
    assert report["months_observed"] == 1


def test_two_nonoverlapping_source_trades_share_capacity():
    rows = bars([
        (100, 100, 100, 100), (100, 102, 98, 100),
        (100, 100, 100, 100), (100, 100, 100, 100),
        (100, 102, 98, 100),
    ])
    report = parity.verify_rows(rows, [candidate(rows, 1), candidate(rows, 4)])
    assert report["source_selected_trades"] == 2
    assert report["fees_usd_per_oz"] == pytest.approx(0.8)
    assert report["net_usd_per_oz"] == pytest.approx(-2.8)


def test_rejects_unsorted_or_crossed_private_quotes_before_parity():
    rows = bars([(100, 100, 100, 100), (100, 100, 100, 100)])
    rows[1]["ao"] = 99.0
    with pytest.raises(ValueError, match="Crossed"):
        parity.verify_rows(rows, [])
    rows = list(reversed(bars([(100, 100, 100, 100), (100, 100, 100, 100)])))
    with pytest.raises(ValueError, match="unsorted"):
        parity.verify_rows(rows, [])


def test_private_archive_sha_rejected_before_opening_or_replaying(tmp_path):
    private = tmp_path / "Gold data.zip"
    private.write_bytes(b"not the private source")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        parity.verify_private_zip(private)


@pytest.mark.parametrize("years", [(2012, 2012), (2000,), (), (True,)])
def test_reject_invalid_year_selection_before_private_source_access(tmp_path, years):
    with pytest.raises(ValueError, match="Years"):
        parity.verify_private_zip(tmp_path / "not-there.zip", years)
