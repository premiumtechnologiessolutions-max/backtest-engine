"""No credentials or live orders: offline OANDA/macro/multi-robot research contracts."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from norisk_quant.oanda_readonly import fetch_practice_m1, parse_closed_m1
from norisk_quant.causal_market_context import Observation, ScheduledEvent, as_of, news_blackout
from norisk_quant.robot_research_lab import RobotSpec, evaluate_robots, robots_from_json
from scripts import run_multi_asset_research as runner


def time(i):
    return pd.Timestamp("2026-10-01T00:00:00Z") + pd.Timedelta(minutes=i)


def candles(n=10):
    rows = []
    for i in range(n):
        bid = 1.0 + i * 0.001
        rows.append({"time": time(i).isoformat(), "complete": True, "volume": 10,
                     "bid": {"o": str(bid), "h": str(bid + .004),
                             "l": str(bid - .001), "c": str(bid + .002)},
                     "ask": {"o": str(bid + .0002), "h": str(bid + .0042),
                             "l": str(bid - .0008), "c": str(bid + .0022)}})
    return {"instrument": "EUR_USD", "candles": rows}


def robot(name="trend_one", family="momentum", spread=.01):
    return RobotSpec(name, "EUR_USD", family, 2, .0001, spread, 0, .003, 2.0)


def test_complete_m1_bid_ask_and_decision_after_close():
    parsed = parse_closed_m1(candles(), "EUR_USD")
    assert len(parsed) == 10
    assert parsed[0].known_at == time(1)
    assert parsed[0].ask_o > parsed[0].bid_o
    bad = candles()
    bad["candles"][-1]["complete"] = False
    with pytest.raises(ValueError, match="Incomplete"):
        parse_closed_m1(bad, "EUR_USD")


@pytest.mark.parametrize("mutation", ("duplicate", "naive", "bad_price", "ask_under_bid", "bool_volume"))
def test_invalid_oanda_candles_rejected(mutation):
    raw = candles()
    if mutation == "duplicate":
        raw["candles"][1]["time"] = raw["candles"][0]["time"]
    elif mutation == "naive":
        raw["candles"][0]["time"] = "2026-10-01T00:00:00"
    elif mutation == "bad_price":
        raw["candles"][0]["bid"]["c"] = "NaN"
    elif mutation == "ask_under_bid":
        raw["candles"][0]["ask"]["o"] = "0.01"
    else:
        raw["candles"][0]["volume"] = True
    with pytest.raises(ValueError):
        parse_closed_m1(raw, "EUR_USD")


def test_practice_adapter_is_get_only_without_secret_in_url():
    requests = []
    def opener(req, timeout):
        requests.append(req)
        return BytesIO(json.dumps(candles(2)).encode())
    result = fetch_practice_m1("EUR_USD", time(0), time(2),
                               bearer_token="TEST_PLACEHOLDER_SECRET", opener=opener)
    assert len(result) == 2
    assert requests[0].get_method() == "GET"
    assert "/v3/instruments/EUR_USD/candles?" in requests[0].full_url
    assert "TEST_PLACEHOLDER_SECRET" not in requests[0].full_url
    with pytest.raises(ValueError, match="1..5000"):
        fetch_practice_m1("EUR_USD", time(0), time(5001), bearer_token="TEST")


def test_macro_asof_must_not_leak_future_revisions():
    first = Observation("policy_rate_EUR", "policy_rate", 3.5, time(1), time(2), "v1", "TEST")
    revision = Observation("policy_rate_EUR", "policy_rate", 4.5, time(1), time(8), "v2", "TEST")
    assert not as_of((first, revision), time(1))
    assert as_of((first, revision), time(5))["policy_rate_EUR"].value == 3.5
    assert as_of((first, revision), time(9))["policy_rate_EUR"].value == 4.5
    with pytest.raises(ValueError, match="before release"):
        Observation("policy_rate_USD", "policy_rate", 2, time(5), time(3), "v1", "TEST")


def test_news_veto_only_after_schedule_announced():
    known = ScheduledEvent("nfp_test", "USD", time(0), time(10), "high", "TEST")
    assert news_blackout((known,), "EUR_USD", time(5), before_minutes=5) == ("nfp_test",)
    assert news_blackout((known,), "EUR_USD", time(4), before_minutes=5) == ()
    with pytest.raises(ValueError, match="after its event"):
        ScheduledEvent("bad_test", "USD", time(11), time(10), "high", "TEST")


def test_conflicting_agents_abstain_duplicate_same_direction_fenced():
    cs = parse_closed_m1(candles(), "EUR_USD")
    opposing = evaluate_robots({"EUR_USD": cs}, (robot(), robot("reversal", "mean_reversion")))
    assert not opposing["intents"]
    assert opposing["counters"]["conflict_abstain"] > 0
    equal = evaluate_robots({"EUR_USD": cs}, (robot(), robot("trend_two")))
    assert equal["intents"]
    assert equal["counters"]["duplicate_same_direction_suppressed"] > 0
    assert equal["broker_order_placement_enabled"] is False
    assert equal["execution_model"] == "NONE_INTENTS_NOT_FILLS"
    assert all(x["status"] == "INTENT_ONLY_NEXT_OPEN_NOT_EXECUTED" for x in equal["intents"])


def test_no_fabricated_rate_signals_and_macro_release_cutoff():
    cs = parse_closed_m1(candles(), "EUR_USD")
    rates = robot("rate_only", "rate_differential")
    assert not evaluate_robots({"EUR_USD": cs}, (rates,))["intents"]
    eur = Observation("policy_rate_EUR", "policy_rate", 4, time(0), time(7), "v1", "ECB")
    usd = Observation("policy_rate_USD", "policy_rate", 3, time(0), time(1), "v1", "FED")
    r = evaluate_robots({"EUR_USD": cs}, (rates,), (eur, usd))
    assert r["intents"] and all(pd.Timestamp(x["confirmed_at"]) >= time(7) for x in r["intents"])


def test_gaps_and_spread_force_abstention():
    raw = candles()
    raw["candles"][4]["time"] = time(14).isoformat()
    truncated = parse_closed_m1({"instrument": "EUR_USD", "candles": raw["candles"][:5]}, "EUR_USD")
    assert evaluate_robots({"EUR_USD": truncated}, (robot(),))["counters"]["blocked_gap"] > 0
    cs = parse_closed_m1(candles(), "EUR_USD")
    assert not evaluate_robots({"EUR_USD": cs}, (robot(spread=.00001),))["intents"]


def test_replay_digest_stable_and_bounded():
    cs = parse_closed_m1(candles(), "EUR_USD")
    a = evaluate_robots({"EUR_USD": cs}, (robot(),))
    assert a == evaluate_robots({"EUR_USD": cs}, (robot(),))
    digest = a.pop("manifest_sha256")
    assert digest == hashlib.sha256(json.dumps(a, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    with pytest.raises(ValueError, match="budget"):
        evaluate_robots({"EUR_USD": cs}, (robot(),), max_intents=1)


def test_offline_cli_outputs_immutable_intents_without_trades(tmp_path):
    r = tmp_path / "robots.json"
    e = tmp_path / "events.json"
    c = tmp_path / "candles.json"
    output = tmp_path / "owner_only"
    r.write_text(json.dumps([{"robot_id":"trend_one","instrument":"EUR_USD",
        "family":"momentum","lookback":2,"threshold":.0001,
        "max_spread_quote":.01,"cooldown_minutes":0,
        "stop_distance_quote":.003}]))
    e.write_text('{"observations":[],"schedules":[]}')
    c.write_text(json.dumps({"EUR_USD": candles()}))
    args = SimpleNamespace(robots=r, context=e, candles=c, practice=False,
                           start=None, end=None, out=output)
    report = runner.run(args)
    assert report["intent_count"] > 0
    doc = json.loads((output / "multi_asset_intents.json").read_text())
    assert doc["broker_order_placement_enabled"] is False
    assert doc["research_profitability_proven"] is False
    with pytest.raises(ValueError, match="already exists"):
        runner.run(args)


def test_bad_robot_spec_and_duplicate_ids_fail_closed():
    raw = {"robot_id":"trend_one","instrument":"EUR_USD","family":"momentum",
           "lookback":2,"threshold":.0001,"max_spread_quote":.01,
           "cooldown_minutes":0,"stop_distance_quote":.003}
    with pytest.raises(ValueError, match="Duplicate"):
        robots_from_json([raw, raw])
    with pytest.raises(ValueError):
        robots_from_json([{**raw, "lookback": True}])


@pytest.mark.parametrize("component", ("o", "h", "l", "c"))
def test_oanda_data_ingress_rejects_any_crossed_bid_ask(component):
    """Crossed highs/lows are as invalid as crossed open/close quotes."""
    raw = candles(2)
    bid = float(raw["candles"][0]["bid"][component])
    # A small undercut preserves independent OHLC geometry for every field.
    raw["candles"][0]["ask"][component] = str(bid - 0.0001)
    with pytest.raises(ValueError, match="ASK below BID"):
        parse_closed_m1(raw, "EUR_USD")


@pytest.mark.parametrize("invalid", ("1e999", "1e-9999", "Infinity", "NaN"))
def test_oanda_data_ingress_rejects_unrepresentable_floats(invalid):
    from norisk_quant.oanda_readonly import decimal_price
    with pytest.raises(ValueError):
        decimal_price(invalid)


def test_oanda_data_ingress_rejects_unaligned_m1_timestamp():
    raw = candles(2)
    raw["candles"][0]["time"] = (time(0) + pd.Timedelta(seconds=30)).isoformat()
    with pytest.raises(ValueError, match="align"):
        parse_closed_m1(raw, "EUR_USD")


def test_oanda_data_ingress_bounded_offline_parser():
    raw = {"instrument": "EUR_USD", "candles": [None] * 5001}
    with pytest.raises(ValueError, match="bounded"):
        parse_closed_m1(raw, "EUR_USD")


def test_oanda_data_ingress_rejects_unaligned_practice_window():
    with pytest.raises(ValueError, match="align"):
        fetch_practice_m1("EUR_USD", time(0) + pd.Timedelta(seconds=1), time(2),
                          bearer_token="NEVER_SENT")
