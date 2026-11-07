import json
import sys

import pandas as pd

from norisk_quant.cli import main


def test_cli_gap_audit_generates_reproducible_catalogue(tmp_path, monkeypatch, capsys):
    timestamps = [
        "2024-01-10T21:59:00Z",
        "2024-01-10T23:00:00Z",
        "2024-01-10T23:01:00Z",
    ]
    epoch = [int(pd.Timestamp(ts).timestamp()) for ts in timestamps]
    df = pd.DataFrame(
        {
            "ts": epoch,
            "o": [100, 100, 100],
            "h": [101, 101, 101],
            "l": [99, 99, 99],
            "c": [100, 100, 100],
            "ao": [100.4, 100.4, 100.4],
            "ah": [101.4, 101.4, 101.4],
            "al": [99.4, 99.4, 99.4],
            "ac": [100.4, 100.4, 100.4],
            "v": [1, 1, 1],
        }
    )
    path = tmp_path / "market.csv"
    out = tmp_path / "output"
    df.to_csv(path, index=False)
    monkeypatch.setattr(
        sys, "argv",
        [
            "norisk", "audit-gaps", "--data", str(path),
            "--start", "2024-01-10", "--end", "2024-01-10",
            "--out", str(out),
        ],
    )
    main()
    printed = json.loads(capsys.readouterr().out)
    assert printed["total_gaps"] == 1
    assert printed["needs_review"] == 0
    assert printed["classification_counts"]["regular_daily_break_pattern"] == 1
    catalog = pd.read_csv(out / "gap_catalogue.csv")
    assert len(catalog) == 1
    assert catalog.iloc[0]["missing_minutes"] == 60
    assert (out / "gap_manual_review.csv").is_file()
