"""Adversarial synthetic-only UTC exit allocation tests; no original Gold replay."""
import copy

import pytest

from norisk_quant.evidence_reconciliation import verify_exit_periods


def example():
    monthly = [
        {"period": "2024-01", "trades": "1", "net_pnl": "3", "total_cost": "0.4"},
        {"period": "2024-02", "trades": "1", "net_pnl": "-2", "total_cost": "0.4"},
    ]
    weekly = [
        {"period": "2024-01-01/2024-01-07", "trades": "1", "net_pnl": "3", "total_cost": "0.4"},
        {"period": "2024-02-05/2024-02-11", "trades": "1", "net_pnl": "-2", "total_cost": "0.4"},
    ]
    trades = [
        {"closed_at": "2024-01-02T12:00:00+00:00", "net_pnl": "3", "cost": "0.4"},
        {"closed_at": "2024-02-06T12:00:00+00:00", "net_pnl": "-2", "cost": "0.4"},
    ]
    return monthly, weekly, trades


def test_valid():
    verify_exit_periods(*example())


@pytest.mark.parametrize("mutate", [
    lambda m,w,t: t[0].update(closed_at="2024-02-02T12:00:00+00:00"),
    lambda m,w,t: t[0].update(closed_at="2024-01-08T12:00:00+00:00"),
    lambda m,w,t: t[0].update(closed_at="2024-01-02T12:00:00"),
    lambda m,w,t: t[0].update(closed_at="2024-01-02T13:00:00+01:00"),
    lambda m,w,t: t[0].update(closed_at="not-a-date"),
    lambda m,w,t: w[0].update(net_pnl="4"),
    lambda m,w,t: m[0].update(total_cost="0.8"),
    lambda m,w,t: w.append(copy.copy(w[0])),
    lambda m,w,t: t.append(copy.copy(t[0])),
    lambda m,w,t: t[0].pop("closed_at"),
    lambda m,w,t: t[0].update(net_pnl="NaN"),
    lambda m,w,t: m.pop(0),
])
def test_rejects_shift_and_tamper(mutate):
    m,w,t = example()
    mutate(m,w,t)
    with pytest.raises(ValueError):
        verify_exit_periods(m,w,t)


def test_empty_trades_with_zero_periods():
    verify_exit_periods(
        [{"period":"2024-01", "trades":"0", "net_pnl":"0", "total_cost":"0"}],
        [{"period":"2024-01-01/2024-01-07", "trades":"0", "net_pnl":"0", "total_cost":"0"}],
        [],
    )


@pytest.mark.parametrize("kind,label", [
    ("month", "2024-13"),
    ("month", "2024-00"),
    ("month", "2024-1"),
    ("month", "0000-01"),
    ("month", "2024-01-01"),
    ("week", "2024-01-02/2024-01-08"),  # Tuesday to Monday
    ("week", "2024-01-01/2024-01-08"),  # eight days
    ("week", "2024-02-30/2024-03-03"),  # impossible date
    ("week", "2024-01-01/2024-01-06"),  # Saturday end
    ("week", "2024-01-01/2024-01-07 "),
])
def test_rejects_malformed_zero_trade_period_labels(kind, label):
    monthly, weekly, trades = example()
    extra = {"period": label, "trades": "0", "net_pnl": "0", "total_cost": "0"}
    if kind == "month":
        monthly.append(extra)
    else:
        weekly.append(extra)
    with pytest.raises(ValueError, match="period|Weekly"):
        verify_exit_periods(monthly, weekly, trades)


def test_accepts_valid_zero_trade_calendar_period():
    monthly, weekly, trades = example()
    monthly.append({"period": "2024-03", "trades": "0", "net_pnl": "0", "total_cost": "0"})
    weekly.append({"period": "2024-01-08/2024-01-14", "trades": "0", "net_pnl": "0", "total_cost": "0"})
    verify_exit_periods(monthly, weekly, trades)
