"""Synthetic contracts for research-only sweep BID/ASK simulator."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
p = Path(__file__).resolve().parents[1] / "scripts" / "simulate_sweep_bid_ask_research.py"
spec = importlib.util.spec_from_file_location("sweep_fill_research", p)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

T = datetime(2026, 10, 30, tzinfo=timezone.utc)
class Signal:
    def __init__(self, side, extreme):
        self.side, self.extreme, self.confirmed_at = side, extreme, T

def q(i, bo=100, bh=101, bl=99, bc=100, ao=100.2, ah=101.2, al=99.2, ac=100.2):
    return m.QuoteBar(T + timedelta(minutes=i), bo, bh, bl, bc, ao, ah, al, ac)

def test_buy_stop_first_when_both_touch():
    out = m.simulate_signal(Signal("BUY", 99.5), [q(0, bh=103, bl=98)])
    assert out.reason == "STOP"
    assert out.entry == 100.2 and out.stop == 99.4
    assert abs(out.net_per_ounce - (-1.2)) < 1e-9

def test_sell_stop_first_when_both_touch():
    out = m.simulate_signal(Signal("SELL", 101.0), [q(0, ah=103, al=98)])
    assert out.reason == "STOP"
    assert out.entry == 100 and out.stop == 101.1
    assert abs(out.net_per_ounce - (-1.5)) < 1e-9

def test_no_fill_if_confirmation_minute_missing():
    assert m.simulate_signal(Signal("BUY", 99), [q(1)]) is None

def test_gap_exits_at_next_available_open_not_ideal_stop():
    out = m.simulate_signal(Signal("BUY", 98), [
        q(0, bh=100.3, bl=99.9),
        q(2, bo=90, bh=91, bl=89, bc=90, ao=90.2, ah=91.2, al=89.2, ac=90.2)])
    assert out.reason == "GAP_OPEN" and out.exit == 90
    assert abs(out.net_per_ounce - (-10.6)) < 1e-9

def test_ask_exit_for_sell_and_fee_once():
    out = m.simulate_signal(Signal("SELL", 102), [q(0, ah=100.8, al=97)])
    assert out.reason == "TARGET"
    assert abs(out.net_per_ounce - (out.gross_per_ounce - 0.4)) < 1e-9

def test_invalid_risk_rejected():
    assert m.simulate_signal(Signal("BUY", 101), [q(0)]) is None
