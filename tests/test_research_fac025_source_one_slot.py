"""Synthetic-only controls for FAC025 source one-slot replay; no raw Gold data."""
from scripts import research_fac025_source_one_slot as fac


def bars(*prices):
    return [{"ts": i * 60, "o": p[0], "h": p[1], "l": p[2], "c": p[3],
             "ao": p[0] + 0.2, "ah": p[1] + 0.2,
             "al": p[2] + 0.2, "ac": p[3] + 0.2}
            for i, p in enumerate(prices)]


def intent(idx, side=1, risk=1.0):
    return {"entry_idx": idx, "entry_at": idx * 60,
            "decision": (idx - 1) * 60, "side": side, "risk": risk,
            "ratios": {4: 0.001}, "ny_hour": 9, "ny_day": "1969-12-31"}


def test_stop_first_both_extremes_and_fixed_fee():
    rows = bars((100, 102, 98, 101), (101, 103, 98, 101))
    trade = fac.settle_trade(rows, intent(0))
    assert trade["exit_reason"] == "stop_first"
    assert trade["exit_price"] == 99 and trade["net"] == -1.4
    assert fac.score(rows, [trade])["fees_usd_per_oz"] == 0.4


def test_adverse_gap_through_not_optimistically_filled_at_stop():
    rows = bars((100, 100.5, 99.8, 100), (97, 98, 96, 97))
    trade = fac.settle_trade(rows, intent(0))
    assert trade["exit_reason"] == "adverse_open_stop"
    assert trade["exit_price"] == 97 and trade["net"] == -3.4


def test_forced_exit_last_observed_and_monthly_equity():
    rows = bars((100, 100.2, 99.9, 100.1), (100.2, 100.4, 100.1, 100.3))
    trade = fac.settle_trade(rows, intent(0, risk=5))
    assert trade["exit_reason"] == "end_of_year_forced"
    result = fac.score(rows, [trade])
    assert result["trades"] == 1 and result["months_observed"] == 1
    assert abs(result["net_usd_per_oz"] - (-0.1)) < 1e-8


def test_one_slot_and_preknown_daily_halt():
    rows = bars(*[(100, 100.1, 99.9, 100) for _ in range(10)])
    p = fac.frozen_specs()[0]["parameters"].copy()
    p["daily_loss_halt"] = "2"
    spec = {"id": "synthetic", "parameters": p}
    first, second = intent(1), intent(2)
    first["decision"] = 0
    second["decision"] = 60
    assert fac.eligible(first, spec, {})
    assert not fac.eligible(second, spec, {"1969-12-31": -3.0})
    selected, info = fac.replay([first, second], rows, [spec])
    assert len(selected) == 1 and info["skipped_capacity"] == 1


def test_frozen_grid_and_reject_crossed_quotes():
    assert len(fac.frozen_specs()) == 72
    rows = bars((100, 100.2, 99.8, 100))
    rows[0].update({"ao": 99.8, "ah": 100.0, "al": 99.6, "ac": 99.8})
    try:
        fac.validate_source(rows)
    except ValueError as exc:
        assert "Crossed" in str(exc)
    else:
        raise AssertionError("crossed quote accepted")
