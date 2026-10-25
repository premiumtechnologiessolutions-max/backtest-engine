import json
import zipfile

import pandas as pd
import pytest

from norisk_quant.data import load_market


def source_row(ts):
    return {
        "ts": ts, "o": 100, "h": 101, "l": 99, "c": 100,
        "ao": 100.4, "ah": 101.4, "al": 99.4, "ac": 100.4,
        "v": 1,
    }


def test_direct_private_zip_import_only_reads_requested_year(tmp_path):
    archive = tmp_path / "Gold data.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(
            "2023.json",
            json.dumps([source_row(int(pd.Timestamp("2023-01-02T00:00Z").timestamp()))]),
        )
        handle.writestr(
            "2024.json",
            json.dumps([
                source_row(int(pd.Timestamp("2024-01-02T00:00Z").timestamp())),
                source_row(int(pd.Timestamp("2024-01-02T00:01Z").timestamp())),
            ]),
        )
    data = load_market(archive, "2024-01-01", "2024-01-31")
    assert len(data) == 2
    assert data.index[0].year == 2024
    assert data["ao"].iloc[0] == pytest.approx(100.4)


def test_direct_zip_rejects_duplicate_year(tmp_path):
    archive = tmp_path / "Gold data.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("2024.json", json.dumps([source_row(1704153600)]))
        handle.writestr("2024 (1).json", json.dumps([source_row(1704153600)]))
    with pytest.raises(ValueError, match="Duplicate year"):
        load_market(archive, "2024-01-01", "2024-12-31")
