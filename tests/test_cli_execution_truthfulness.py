"""CLI must not misreport which execution engine or strategy gates ran.

All cases fail during argument validation, before accessing market data.
"""
import sys

import pytest

from norisk_quant.cli import main


BASE = [
    "norisk", "backtest",
    "--data", "/does-not-exist/private-gold.zip",
    "--start", "2024-01-01", "--end", "2024-01-31",
    "--out", "/unused",
]


@pytest.mark.parametrize("strategy", ["bos-fib", "fvg"])
def test_limit_strategy_rejects_silently_ignored_fast_engine(monkeypatch, capsys, strategy):
    monkeypatch.setattr(sys, "argv", BASE + [
        "--strategy", strategy, "--timeframe", "M1", "--execution", "fast",
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "--execution fast is not implemented for limit strategies" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--strategy", "bos-fib", "--bos-h1-max-age-minutes", "120"],
         "--bos-h1-max-age-minutes requires --bos-require-h1-trend"),
        (["--strategy", "bos-fib", "--bos-require-h1-trend",
          "--bos-h1-max-age-minutes", "-1"],
         "--bos-h1-max-age-minutes must be nonnegative"),
        (["--strategy", "ema", "--bos-require-h1-trend"],
         "BOS/H1 filters require --strategy bos-fib"),
        (["--strategy", "fvg", "--bos-ignore-dual-pivots"],
         "BOS/H1 filters require --strategy bos-fib"),
        (["--strategy", "qs01", "--timeframe", "M1",
          "--bos-h1-max-age-minutes", "120"],
         "BOS/H1 filters require --strategy bos-fib"),
    ],
)
def test_invalid_bos_controls_rejected_before_market_io(monkeypatch, capsys, extra, message):
    monkeypatch.setattr(sys, "argv", BASE + extra)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert message in capsys.readouterr().err
