"""Synthetic regressions: raw mixed booleans must never become valid BID/ASK 0/1."""
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from norisk_quant.data import import_gold_zip, normalize, read_source


def _raw():
    # All quote fields can legitimately be 1.0, so a coerced True would
    # pass the ordinary price/OHLC/crossed-quote checks undetected.
    return pd.DataFrame([
        {"ts": 1577836800, **{key: 1.0 for key in
          ("o", "h", "l", "c", "ao", "ah", "al", "ac")}},
        {"ts": 1577836860, **{key: 1.0 for key in
          ("o", "h", "l", "c", "ao", "ah", "al", "ac")}},
    ])


@pytest.mark.parametrize("column", ["ts", "o", "h", "l", "c", "ao", "ah", "al", "ac"])
@pytest.mark.parametrize("boolean", [True, False, np.bool_(True)])
@pytest.mark.parametrize("strict", [True, False])
def test_mixed_boolean_raw_cells_rejected_before_numeric_coercion(
    column, boolean, strict
):
    raw = _raw()
    raw[column] = raw[column].astype(object)
    raw.at[0, column] = boolean
    with pytest.raises(ValueError, match="numeric non-boolean"):
        normalize(raw, strict=strict)


@pytest.mark.parametrize("column", ["ts", "o", "ah"])
def test_json_mixed_boolean_source_is_rejected(tmp_path, column):
    raw = _raw()
    rows = raw.to_dict("records")
    rows[0][column] = False
    path = tmp_path / "source.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="numeric non-boolean"):
        read_source(path)


def test_zip_import_rejects_mixed_boolean_before_parquet_cache(tmp_path):
    rows = _raw().to_dict("records")
    rows[0]["al"] = True
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("2020.json", json.dumps(rows))
    out = tmp_path / "cache"
    with pytest.raises(ValueError, match="numeric non-boolean"):
        import_gold_zip(archive, out)
    assert not list(out.glob("*.parquet"))


def test_numeric_text_source_still_supported_without_boolean_coercion():
    raw = _raw()
    raw["ao"] = raw["ao"].map(lambda v: str(v))
    clean = normalize(raw)
    assert len(clean) == 2
    assert clean["ao"].tolist() == [1.0, 1.0]
