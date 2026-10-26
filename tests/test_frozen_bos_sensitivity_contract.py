import pandas as pd
import pytest

import scripts.run_bos_fib_frozen_sensitivity as frozen
from scripts.run_bos_fib_frozen_sensitivity import (
    EXECUTION_SETTINGS, H1_SETTINGS, SOURCE_SHA, YEARLY_SETTINGS,
    validate_annual_month_coverage, validate_year_selection,
)


def test_frozen_bos_sensitivity_configuration_cannot_silently_drift():
    assert YEARLY_SETTINGS.fib_entry == 0.618
    assert YEARLY_SETTINGS.reward_risk == 1
    assert YEARLY_SETTINGS.ignore_ambiguous_dual_pivots
    assert H1_SETTINGS.max_regime_age_minutes == 120
    assert H1_SETTINGS.ema_span == 50
    assert H1_SETTINGS.slope_lag_bars == 5
    assert EXECUTION_SETTINGS.ounces == 1.0
    assert EXECUTION_SETTINGS.roundtrip_cost_per_ounce == 0.40
    assert len(SOURCE_SHA) == 64


@pytest.mark.parametrize("years", [
    [], [2012, 2012], [2009], [2027], [2012, 2012, 2020],
])
def test_frozen_year_selection_rejects_duplicate_and_outside_source(years):
    with pytest.raises(ValueError):
        validate_year_selection(years)


def test_frozen_year_selection_accepts_separate_exposed_years():
    validate_year_selection([2012, 2017, 2020, 2024])


@pytest.mark.parametrize("years", [
    [True], [2012.0], [float("nan")], ["2012"], [2012, False],
])
def test_frozen_year_selection_rejects_coerced_calendar_years(years):
    with pytest.raises(ValueError, match="integer calendar years"):
        validate_year_selection(years)


def _monthly_sample(year=2012):
    # One observation per month deliberately proves only month presence,
    # not a complete broker calendar or contiguous minute history.
    return pd.DataFrame(
        {"o": [2000.0] * 12},
        index=pd.date_range(f"{year}-01-01T00:00:00Z", periods=12, freq="MS"),
    )


def test_frozen_annual_month_presence_accepts_twelve_observed_months():
    validate_annual_month_coverage(_monthly_sample(), 2012)


@pytest.mark.parametrize("missing_month", [1, 6, 12])
def test_frozen_annual_month_presence_rejects_missing_month(missing_month):
    sample = _monthly_sample()
    sample = sample.loc[sample.index.month != missing_month]
    with pytest.raises(ValueError, match=f"omits calendar months: \\[({missing_month})\\]"):
        validate_annual_month_coverage(sample, 2012)


def test_frozen_annual_month_presence_rejects_wrong_year_and_bad_index():
    sample = _monthly_sample()
    with pytest.raises(ValueError, match="outside 2013"):
        validate_annual_month_coverage(sample, 2013)
    sample.index = sample.index.tz_localize(None)
    with pytest.raises(ValueError, match="sorted unique UTC"):
        validate_annual_month_coverage(sample, 2012)
    duplicate = pd.concat([_monthly_sample(), _monthly_sample().iloc[:1]])
    with pytest.raises(ValueError, match="sorted unique UTC"):
        validate_annual_month_coverage(duplicate, 2012)


def test_frozen_runner_rejects_missing_month_before_strategy_or_report(tmp_path, monkeypatch):
    source = tmp_path / "synthetic_private_fixture.zip"
    source.write_bytes(b"not actual market data")
    monkeypatch.setattr(frozen, "sha256_file", lambda _: SOURCE_SHA)
    missing = _monthly_sample().loc[lambda frame: frame.index.month != 6]
    monkeypatch.setattr(frozen, "load_market", lambda *args, **kwargs: missing)
    monkeypatch.setattr(
        frozen, "bos_fib_limit_orders",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Strategy must not run with a missing month")
        ),
    )
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="omits calendar months"):
        frozen.execute(source, [2012], output)
    assert not (output / "2012").exists()
    assert not (output / "frozen_sensitivity_summary.json").exists()


def test_frozen_runner_synthetic_end_to_end_writes_reconciled_reports(tmp_path, monkeypatch):
    """Exercise the ACTUAL runner stack on artificial M1, never claim real-ZIP parity.

    Only the immutable private ZIP SHA precondition is mocked; the loader,
    BOS builder, H1 filter, execution simulator and reporting are real.
    Eight contiguous minutes per calendar month intentionally yield zero
    BOS trades; this tests no-trade accounting and complete report writing.
    """
    import json
    import zipfile

    source = tmp_path / "SYNTHETIC_NOT_REAL_GOLD.zip"
    rows = []
    for month in range(1, 13):
        start = pd.Timestamp(year=2012, month=month, day=2, tz="UTC")
        for minute in range(8):
            timestamp = int((start + pd.Timedelta(minutes=minute)).timestamp())
            rows.append({
                "ts": timestamp,
                "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0,
                "ao": 100.4, "ah": 101.4, "al": 99.4, "ac": 100.4,
            })
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("2012.json", json.dumps(rows))
    monkeypatch.setattr(frozen, "sha256_file", lambda _: SOURCE_SHA)
    output = tmp_path / "reports"
    result = frozen.execute(source, [2012], output)
    assert result["status"] == "ACCOUNTING_RECONCILED_NOT_BROKER_CERTIFIED"
    assert result["years_visited_independently"] == [2012]
    assert result["sampled_months"] == 12
    assert result["trades_total"] == 0
    assert result["sum_of_separate_annual_net_usd_1oz"] == 0
    assert result["not_clean_out_of_sample"] is True
    assert result["broker_tick_execution_verification"] is False
    annual = json.loads((output / "2012" / "summary.json").read_text())
    assert annual["trades"] == 0
    assert annual["months_observed"] == 12
    assert annual["months_with_m1_observations"] == 12
    assert annual["source_fingerprints"]["loaded_m1_rows"] == 96
    assert len(annual["source_fingerprints"]["loaded_m1_bidask_sha256"]) == 64
    assert len(pd.read_csv(output / "2012" / "monthly.csv")) == 12
    assert (output / "2012" / "weekly.csv").is_file()
    assert (output / "2012" / "equity_m1.csv").is_file()
    assert (output / "2012" / "trades.csv").is_file()
    assert (output / "frozen_sensitivity_summary.json").is_file()
