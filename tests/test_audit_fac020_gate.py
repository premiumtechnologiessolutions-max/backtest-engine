"""Synthetic-only tests: do not rely on the private gold archive."""
import copy
import pytest
from scripts.audit_fac020_gate import MONTHS, audit


def sample():
    a, b, c = [], [], []
    for name, pnl, trades in (("A", 1.0, 110), ("B", -1.0, 12)):
        for year, dest in ((2012, a), (2013, b)):
            annual = {"id": name, "rule_id": f"RULE_{name}",
                      "trades": str(trades), "fees_usd": str(.4 * trades),
                      "net_usd_oz": str(pnl * 12), "max_m1_dd": "4"}
            annual.update({m: str(pnl) for m in MONTHS})
            dest.append(annual)
        c.append({"id": name, "rule_id": f"RULE_{name}",
                  "positive_months": str(24 if pnl > 0 else 0),
                  "net_2012": str(pnl * 12), "net_2013": str(pnl * 12),
                  "net_total": str(pnl * 24), "worst_month": str(pnl),
                  "max_annual_floating_dd": "4", "trades_2012": str(trades),
                  "trades_2013": str(trades), "fees_total": str(.8 * trades),
                  "passed": str(pnl > 0)})
    return a, b, c


def test_reconcile_and_frozen_gate():
    result = audit(*sample())
    assert result["distinct_correlated_parameter_specs"] == 2
    assert result["monthly_values_reconciled"] == 48
    assert result["specs_passing_frozen_joint_gate"] == 1
    assert result["max_positive_months"] == 24
    assert result["individual_gate_pass_counts"]["fills"] == 1


@pytest.mark.parametrize("mutate", [
    lambda x: x[0][0].update({"m01": "2"}),
    lambda x: x[0][0].update({"fees_usd": "0"}),
    lambda x: x[1][0].update({"trades": "NaN"}),
    lambda x: x[2][0].update({"net_total": "999"}),
    lambda x: x[2][0].update({"passed": "False"}),
    lambda x: x[2][0].update({"worst_month": "-999"}),
    lambda x: x[1][0].update({"rule_id": "DIFFERENT"}),
    lambda x: x[0].append(copy.deepcopy(x[0][0])),
    lambda x: x[1].pop(),
])
def test_reject_corrupt_exports(mutate):
    rows = sample()
    mutate(rows)
    with pytest.raises(ValueError):
        audit(*rows)
