"""Adversarial training evidence checks: never rank incomplete/tampered years."""
import copy
import pytest

from norisk_quant.research_training_integrity import training_summary


def record(year, pnl=1.0, trades=45):
    months = {f"{year}-{m:02d}": pnl for m in range(1, 13)}
    return {"year": year, "metrics": {
        "months": months, "net_usd_per_oz": pnl * 12,
        "trades": trades, "fees_usd": trades * .40,
        "positive_months": 12 if pnl > 0 else 0,
        "uncertain_gap_trades": 0, "synthetic_forced_closures": 0,
        "accounting": "PASSED"}}


def test_complete_training_rank_is_order_invariant_and_not_oos():
    records = [record(2012), record(2013)]
    a = training_summary(records, (2012, 2013))
    assert a == training_summary(records[::-1], (2012, 2013))
    assert a["total_months"] == 24 and a["positive_months"] == 24
    assert a["net_usd_per_oz"] == 24
    assert a["screen"] == "PASSED_TRAIN_HEURISTIC_NOT_OOS"
    assert a["independent_oos_proven"] is False
    assert a["market_edge_confirmed"] is False


def test_negative_or_gap_exposure_cannot_pass():
    assert training_summary([record(2012, -1), record(2013, -1)],
                            (2012, 2013))["screen"] == "REJECTED_TRAIN_HEURISTIC"
    rows = [record(2012), record(2013)]
    rows[0]["metrics"]["uncertain_gap_trades"] = 1
    assert training_summary(rows, (2012, 2013))["screen"] == "REJECTED_TRAIN_HEURISTIC"


@pytest.mark.parametrize("change", [
    lambda r: r[0]["metrics"]["months"].update({"2014-01": 1}),
    lambda r: r[0]["metrics"]["months"].pop("2012-01"),
    lambda r: r[0]["metrics"]["months"].__setitem__("2012-01", True),
    lambda r: r[0]["metrics"]["months"].__setitem__("2012-01", float("nan")),
    lambda r: r[0]["metrics"].__setitem__("net_usd_per_oz", 999),
    lambda r: r[0]["metrics"].__setitem__("fees_usd", 0),
    lambda r: r[0]["metrics"].__setitem__("positive_months", 5),
    lambda r: r[0]["metrics"].__setitem__("trades", -1),
    lambda r: r[0]["metrics"].__setitem__("uncertain_gap_trades", 46),
    lambda r: r[0]["metrics"].__setitem__("synthetic_forced_closures", 46),
    lambda r: r[0]["metrics"].__setitem__("accounting", "UNKNOWN"),
    lambda r: r[0].__setitem__("year", 2014),
    lambda r: r[0].__setitem__("year", True),
])
def test_bad_accounting_never_enters_rank(change):
    rows = [record(2012), record(2013)]
    change(rows)
    with pytest.raises(ValueError):
        training_summary(rows, (2012, 2013))


def test_no_trade_hypothesis_always_ranked_below_observed_candidates():
    rows = [record(2012, 0, 0), record(2013, 0, 0)]
    result = training_summary(rows, (2012, 2013))
    assert result["training_score"] < -1000
    assert result["screen"] == "REJECTED_TRAIN_HEURISTIC"


@pytest.mark.parametrize("years", [
    (2013, 2012), (2012, 2012), (2012, True), [2012, 2013], (2012,), (),
])
def test_year_universe_must_be_frozen(years):
    with pytest.raises(ValueError):
        training_summary([record(2012), record(2013)], years)


def test_review_year_cannot_be_injected_as_training_observation():
    rows = [record(2012), record(2013), record(2014, 1000)]
    with pytest.raises(ValueError):
        training_summary(rows, (2012, 2013))


def test_noncanonical_fee_is_never_silently_used():
    with pytest.raises(ValueError):
        training_summary([record(2012), record(2013)],
                         (2012, 2013), fee_per_trade=0)


def test_overflowed_combined_year_results_are_rejected():
    rows = [record(2012), record(2013)]
    for row in rows:
        year = row["year"]
        row["metrics"]["months"] = {
            f"{year}-{m:02d}": (1e308 if m == 1 else 0.)
            for m in range(1, 13)}
        row["metrics"]["net_usd_per_oz"] = 1e308
        row["metrics"]["positive_months"] = 1
    with pytest.raises(ValueError):
        training_summary(rows, (2012, 2013))


def test_finite_months_can_still_overflow_month_end_drawdown():
    """Each annual net and every month is finite; cross-year drawdown is not."""
    rows = [record(2012, 0.), record(2013, 0.)]
    for row in rows:
        year = row["year"]
        months = {f"{year}-{m:02d}": 0. for m in range(1, 13)}
        if year == 2012:
            months[f"{year}-01"] = 1e308
            months[f"{year}-02"] = -1e308
        else:
            months[f"{year}-01"] = -1e308
            months[f"{year}-02"] = 1e308
        row["metrics"]["months"] = months
        row["metrics"]["net_usd_per_oz"] = 0.
        row["metrics"]["positive_months"] = 1
    with pytest.raises(ValueError, match="drawdown overflowed"):
        training_summary(rows, (2012, 2013))
