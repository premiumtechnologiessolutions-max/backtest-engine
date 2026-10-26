"""FAC006 frozen shared-capacity portfolio and independent canonical control."""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.strategy import aggregate_bars
from scripts.run_fac006_shared_portfolio import (
    FROZEN, build_signals, run_frozen,
)


def fixture(hours=220):
    idx = pd.date_range("2012-01-09T00:00:00Z", periods=hours*60, freq="min")
    step = np.arange(len(idx), dtype=float)
    price = 1650 + 5*np.sin(step*2*np.pi/(15*22)) + .004*step/60
    return pd.DataFrame({"o":price,"h":price+.30,"l":price-.30,"c":price},index=idx)


def test_immutable_signal_names_and_frozen_capacity():
    assert tuple(FROZEN["signals"]) == ("A_RANGE_SLOW","B_RANGE_FAST","C_RSI_BASE")
    assert FROZEN["primary_capacity"] == {"max_positions":1,"max_total_ounces":1.}
    assert FROZEN["unconstrained_parity_control"] == {"max_positions":3,"max_total_ounces":3.}
    assert FROZEN["all_in_fee_per_ounce"] == .40


def test_signals_are_fully_closed_M15_and_timezone_aware():
    m1 = fixture()
    components = build_signals(m1)
    assert set(components) == set(FROZEN["signals"])
    complete = set(aggregate_bars(m1,"M15")["close_at"])
    for name,signals in components.items():
        assert len(signals)>0,name
        assert all(sig.strategy==name for sig in signals)
        assert all(sig.confirmed_at in complete for sig in signals)
        assert all(sig.confirmed_at.tzinfo is not None for sig in signals)


def test_future_m1_does_not_change_prior_frozen_signals():
    m1=fixture()
    full=build_signals(m1)
    partial=m1.iloc[:160*60]
    past=build_signals(partial)
    cutoff=partial.index[-1]+pd.Timedelta(minutes=1)
    for name in FROZEN["signals"]:
        before=[(s.confirmed_at,s.side) for s in full[name] if s.confirmed_at<=cutoff]
        truncated=[(s.confirmed_at,s.side) for s in past[name]]
        assert before==truncated


def test_joint_portfolio_one_slot_and_three_slot_canonical_parity(tmp_path):
    summary=run_frozen(fixture(),year=2012,out=tmp_path/"FAC006")
    control=summary["unconstrained_canonical_parity"]
    assert control["max_monthly_net_delta"]<1e-7
    assert control["max_observed_m1_equity_delta"]<1e-7
    assert control["shared_three_slot_capacity_rejected"]==0
    assert summary["primary_accounting"]["max_observed_open_positions"]<=1
    assert summary["primary_accounting"]["max_observed_open_ounces"]<=1.
    assert (tmp_path/"FAC006"/"primary_one_slot"/"monthly.csv").is_file()
    assert (tmp_path/"FAC006"/"control_three_slots"/"equity_m1.csv").is_file()


def test_reject_nonfrozen_year(tmp_path):
    with pytest.raises(ValueError):
        run_frozen(fixture(),year=2017,out=tmp_path/"wrong")
