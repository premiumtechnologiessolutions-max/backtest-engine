"""Seeded synthetic M1 execution stress; self-contained, no licensed quote files."""
import numpy as np
import pandas as pd

from norisk_quant.limit_engine import LimitOrder, run_limits
from norisk_quant.model import Settings


def test_30_seeded_quote_and_limit_sequences_reconcile():
    for seed in range(30):
        rng = np.random.default_rng(seed)
        minutes = pd.date_range("2020-01-02T00:00:00Z", periods=260, freq="min")
        reference = 100 + np.cumsum(rng.normal(0, 0.1, len(minutes)))
        bars = pd.DataFrame({
            "o": reference,
            "h": reference + rng.random(len(minutes)) * 0.4,
            "l": reference - rng.random(len(minutes)) * 0.4,
            "c": reference,
        }, index=minutes)
        pending = []
        for number in range(1, 35):
            at = minutes[number * 6]
            entry = float(reference[number * 6])
            side = 1 if number % 2 else -1
            pending.append(LimitOrder(
                placed_at=at, expires_at=at + pd.Timedelta(minutes=10),
                side=side, price=entry,
                stop=entry - side * 0.3,
                target=entry + side * 0.4,
                strategy=f"seed{seed}_signal{number}",
            ))
        result = run_limits(bars, pending, Settings())
        assert np.allclose(
            result.equity["realized_pnl"] + result.equity["floating_pnl"],
            result.equity["equity"], rtol=0, atol=1e-7,
        )
        assert result.trades["cost"].eq(0.40).all()
        assert np.allclose(
            result.trades["gross_pnl"] - result.trades["cost"],
            result.trades["net_pnl"], rtol=0, atol=1e-7,
        )
        assert np.isclose(
            result.equity["equity"].iloc[-1],
            result.trades["net_pnl"].sum(), atol=1e-7,
        )
        assert (result.trades["entry_at"] >= result.trades["signal_at"]).all()
        assert (result.trades["closed_at"] >= result.trades["entry_at"]).all()
        assert result.uncertain_entry_tp_deferred >= 0
