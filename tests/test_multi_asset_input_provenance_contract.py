"""A research report must bind all source evidence, not only emitted intents."""
from dataclasses import replace
import pandas as pd

from norisk_quant.oanda_readonly import ClosedCandle
from norisk_quant.robot_research_lab import RobotSpec, evaluate_robots


def candles(close=2000.0):
    result = []
    for i in range(3):
        t = pd.Timestamp("2026-11-01T00:00:00Z") + pd.Timedelta(minutes=i)
        bid = close if i == 2 else 2000.0
        result.append(ClosedCandle(
            "XAU_USD", t, bid, bid, bid, bid,
            bid + .5, bid + .5, bid + .5, bid + .5, 1))
    return tuple(result)


def test_different_source_quotes_cannot_share_same_manifest_fingerprint():
    robot = RobotSpec("gold_trial", "XAU_USD", "momentum", 2, 0.5,
                      2.0, 0, 10.0)
    a = evaluate_robots({"XAU_USD": candles()}, (robot,))
    b = evaluate_robots({"XAU_USD": candles(2001.0)}, (robot,))
    assert a["intents"] == b["intents"] == []
    assert a["counters"] == b["counters"]
    assert a["manifest_sha256"] != b["manifest_sha256"]
    assert a["input_hashes"]["closed_m1_bidask_sha256"] != b["input_hashes"]["closed_m1_bidask_sha256"]


def test_decision_policy_is_part_of_input_provenance():
    robot = RobotSpec("gold_trial", "XAU_USD", "momentum", 2, 0.5,
                      2.0, 0, 10.0)
    a = evaluate_robots({"XAU_USD": candles()}, (robot,), news_before_minutes=15)
    b = evaluate_robots({"XAU_USD": candles()}, (robot,), news_before_minutes=30)
    assert a["input_hashes"]["decision_policy_sha256"] != b["input_hashes"]["decision_policy_sha256"]
    assert a["manifest_sha256"] != b["manifest_sha256"]
