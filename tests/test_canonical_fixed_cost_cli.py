import sys

import pytest

from norisk_quant.cli import main


@pytest.mark.parametrize("fee", ["0", "0.20", "0.80", "-0.1"])
def test_canonical_backtest_refuses_other_costs_before_loading_market(monkeypatch, fee):
    monkeypatch.setattr(sys, "argv", [
        "norisk", "backtest",
        "--data", "/a/private/file/that/does/not/exist.zip",
        "--start", "2024-01-01", "--end", "2024-01-31",
        "--out", "/tmp/not-created",
        "--all-in-cost-per-ounce", fee,
    ])
    with pytest.raises(SystemExit, match="2"):
        main()
