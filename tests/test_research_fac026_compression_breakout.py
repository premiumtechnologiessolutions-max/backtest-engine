"""Synthetic causality and grid controls for frozen FAC026 (NO market replay)."""
from datetime import datetime, timedelta, timezone
import pytest
from scripts.research_fac026_compression_breakout import evaluate, frozen_specs

UTC = timezone.utc
END = datetime(2026, 10, 29, 13, 15, tzinfo=UTC)
SIGNAL = END + timedelta(minutes=1)


def candle(end, o, h, l, c, count):
    return {"end_at": end, "open": o, "high": h, "low": l,
            "close": c, "observed_m1_count": count}


def fixture(side=1):
    # 8 baseline wide bars, 8 compressed narrow bars, then a breakout.
    m = []
    for i in range(17):
        end = END - timedelta(minutes=(16 - i) * 15)
        if i < 8:
            m.append(candle(end, 100, 101, 99, 100, 15))
        elif i < 16:
            m.append(candle(end, 100, 100.4, 99.6, 100, 15))
        else:
            if side == 1:
                m.append(candle(end, 100.42, 100.57, 100.41, 100.55, 15))
            else:
                m.append(candle(end, 99.58, 99.59, 99.43, 99.45, 15))
    # Last completed H1 ends 13:00, strictly before trigger M15 end 13:15.
    h = []
    for i in range(3):
        end = datetime(2026, 10, 29, 11 + i, tzinfo=UTC)
        if side == 1:
            h.append(candle(end, 99.5 + i, 100.5 + i, 99.5 + i,
                            100.5 + i, 60))
        else:
            h.append(candle(end, 102.5 - i, 102.5 - i, 101.5 - i,
                            101.5 - i, 60))
    return m, h


def spec():
    return next(s for s in frozen_specs() if s["params"]["window"] == 8
                and s["params"]["compression"] == 0.65
                and s["params"]["h1_efficiency"] == 0.35
                and s["params"]["session"] == [9, 13]
                and s["params"]["daily_loss_halt"] == 2.0)


def test_frozen_grid_32_correlated_not_independent():
    a, b = frozen_specs(), frozen_specs()
    assert len(a) == len({s["fingerprint"] for s in a}) == 32
    assert a == b


@pytest.mark.parametrize("side", [1, -1])
def test_causal_breakout_is_research_intent_only(side):
    m, h = fixture(side)
    result = evaluate(SIGNAL, m, h, [], spec=spec())
    assert result["status"] == "ELIGIBLE_RESEARCH_INTENT_ONLY"
    assert result["side"] == side
    assert result["execution"] == "RESEARCH_ONLY_NO_ORDERS"
    assert result["normalized_risk"] > 0


def test_unfrozen_parameters_fail_closed():
    m, h = fixture()
    s = spec()
    s["params"]["compression"] = 0.99
    with pytest.raises(ValueError, match="Unfrozen"):
        evaluate(SIGNAL, m, h, [], spec=s)


@pytest.mark.parametrize("change,reason", [
    ("incomplete", "INCOMPLETE_OBSERVED_M1"),
    ("gap", "M15_GAP"),
    ("compression", "NO_PREKNOWN_VOLATILITY_COMPRESSION"),
    ("h1_direction", "H1_DIRECTION_EFFICIENCY_MISMATCH"),
    ("risk", "NORMALIZED_RISK_TOO_HIGH"),
])
def test_preknown_fail_closed(change, reason):
    m, h = fixture()
    if change == "incomplete":
        m[-2]["observed_m1_count"] = 14
    elif change == "gap":
        for bar in m[:-4]:
            bar["end_at"] -= timedelta(minutes=15)
    elif change == "compression":
        for x in m[8:16]:
            x["high"], x["low"] = 101, 99
    elif change == "h1_direction":
        for x in h:
            x["open"], x["high"], x["low"], x["close"] = 100, 101, 99, 99.5
    elif change == "risk":
        m[-1]["high"], m[-1]["low"] = 101.2, 100.3
    assert evaluate(SIGNAL, m, h, [], spec=spec())["reason"] == reason


def test_same_instant_and_future_bar_rejected():
    m, h = fixture()
    m[-1]["end_at"] = SIGNAL
    with pytest.raises(ValueError, match="future, same-instant"):
        evaluate(SIGNAL, m, h, [], spec=spec())


def test_daily_halt_uses_only_closed_trades():
    m, h = fixture()
    trades = [{"closed_at": SIGNAL - timedelta(minutes=2),
               "net_usd_per_oz": -2.0}]
    assert evaluate(SIGNAL, m, h, trades, spec=spec())["reason"] == "PREKNOWN_DAILY_LOSS_HALT"
    trades[0]["closed_at"] = SIGNAL
    with pytest.raises(ValueError, match="Future"):
        evaluate(SIGNAL, m, h, trades, spec=spec())


def test_dst_local_session_changes_without_fixed_utc_offset():
    m, h = fixture()
    assert evaluate(SIGNAL, m, h, [], spec=spec())["status"] == "ELIGIBLE_RESEARCH_INTENT_ONLY"
    # 13:16 UTC is 09:16 New York during EDT; 08:16 in EST.
    winter_end = END.replace(month=11, day=5)
    shift = winter_end - END
    m2 = [{**b, "end_at": b["end_at"] + shift} for b in m]
    h2 = [{**b, "end_at": b["end_at"] + shift} for b in h]
    assert evaluate(SIGNAL + shift, m2, h2, [], spec=spec())["reason"] == "OUTSIDE_NY_SESSION"


def test_nonfinite_and_boolean_quote_rejected():
    m, h = fixture()
    m[-1]["close"] = True
    with pytest.raises(ValueError, match="finite"):
        evaluate(SIGNAL, m, h, [], spec=spec())
