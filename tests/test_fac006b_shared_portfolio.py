"""FAC006B exact three-slot reference parity and one-slot capacity."""
import numpy as np
import pandas as pd
import pytest

from scripts.run_fac006b_canonical_pending_portfolio import (
    FROZEN, run_frozen,
)


def fixture():
    idx=pd.date_range("2012-01-09T00:00:00Z",periods=220*60,freq="min")
    step=np.arange(len(idx),dtype=float)
    p=1650+5*np.sin(step*2*np.pi/(15*22))+.004*step/60
    return pd.DataFrame({
        "o":p,"h":p+.3,"l":p-.3,"c":p,
        "ao":p+.1,"ah":p+.4,"al":p-.2,"ac":p+.1,
    },index=idx)


def test_optin_policy_is_frozen_and_distinct_from_fac006():
    assert FROZEN["research_id"]=="NRF-FAC-006B"
    assert FROZEN["same_strategy_pending_policy"].startswith("explicit opt-in")
    assert tuple(FROZEN["signals"])==("A_RANGE_SLOW","B_RANGE_FAST","C_RSI_BASE")


def test_canonical_pending_portfolio_matches_independent_fast_engine(tmp_path):
    summary=run_frozen(fixture(),year=2012,out=tmp_path/"portfolio")
    parity=summary["unconstrained_canonical_parity"]
    assert parity["canonical_reference_trades"]==parity["shared_three_slot_trades"]
    assert parity["max_monthly_net_delta"]<1e-7
    assert parity["max_observed_m1_equity_delta"]<1e-7
    assert parity["shared_three_slot_capacity_rejected"]==0
    assert summary["primary_accounting"]["max_observed_open_positions"]<=1
    assert (tmp_path/"portfolio"/"primary_one_slot"/"monthly.csv").exists()
    assert (tmp_path/"portfolio"/"control_three_slots"/"trades.csv").exists()


def test_year_restriction_is_enforced(tmp_path):
    with pytest.raises(ValueError):
        run_frozen(fixture(),year=2024,out=tmp_path/"wrong")
