import pandas as pd
import pytest

from norisk_quant.data import fingerprint_loaded_m1, normalize
from norisk_quant.execution import run
from norisk_quant.model import Settings, Signal
from norisk_quant.report import report


def gold_utc_m1():
    return normalize(pd.DataFrame([
        {"ts": 1704153600, "o": 2000, "h": 2001, "l": 1999,
         "c": 2000.5, "ao": 2000.4, "ah": 2001.4,
         "al": 1999.4, "ac": 2000.9},
        {"ts": 1704153660, "o": 2000.5, "h": 2002, "l": 2000,
         "c": 2001, "ao": 2000.9, "ah": 2002.4,
         "al": 2000.4, "ac": 2001.4},
    ]))


def test_market_data_fingerprint_is_stable_for_identical_content():
    data = gold_utc_m1()
    value = fingerprint_loaded_m1(data)
    assert len(value) == 64
    assert value == fingerprint_loaded_m1(data.copy())


def test_market_data_fingerprint_detects_a_single_ask_quote_revision():
    data = gold_utc_m1()
    revised = data.copy()
    revised.loc[revised.index[0], "ac"] += 0.01
    assert fingerprint_loaded_m1(data) != fingerprint_loaded_m1(revised)


def test_market_data_fingerprint_detects_timestamp_revision():
    data = gold_utc_m1()
    modified = data.copy()
    modified.index = modified.index + pd.Timedelta(minutes=1)
    assert fingerprint_loaded_m1(data) != fingerprint_loaded_m1(modified)


def test_market_data_fingerprint_rejects_unaligned_or_missing_columns():
    data = gold_utc_m1()
    invalid = data.copy()
    invalid.index = invalid.index + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="minute opens"):
        fingerprint_loaded_m1(invalid)
    with pytest.raises(ValueError, match="original Bid/Ask"):
        fingerprint_loaded_m1(data.drop(columns=["ao"]))


def test_summary_persists_parameters_and_dataset_fingerprint(tmp_path):
    data = gold_utc_m1()
    signals = [
        Signal(data.index[0] + pd.Timedelta(minutes=1), 1, 2, 4, "unit")
    ]
    result = run(data, signals, Settings())
    fingerprint = fingerprint_loaded_m1(data)
    params = {"strategy": "unit", "timeframe": "M1", "all_in_cost_per_ounce": 0.40}
    audit = report(
        result, Settings(), tmp_path, source="fixture",
        provenance={"loaded_m1_bidask_sha256": fingerprint, "loaded_m1_rows": 2},
        run_parameters=params,
    )
    assert audit["source_fingerprints"]["loaded_m1_bidask_sha256"] == fingerprint
    assert audit["run_parameters"] == params
    assert (tmp_path / "summary.json").exists()
