"""Synthetic research replay tests; no quotes, brokerage orders or providers."""
import pytest

from norisk_quant.causal_stream_merge import CausalEvent, merge_causal_streams

H = "a" * 64


def event(source, event_at, known_at, seq, values=(1.0,)):
    return CausalEvent(source=source, source_sha256=H, kind="research_quote",
                       event_at_ns=event_at, available_at_ns=known_at,
                       sequence=seq, values=values)


def test_same_clock_stream_priority_is_explicit():
    gold = [event("gold", 5, 10, 0)]
    macro = [event("macro", 5, 10, 0)]
    got = list(merge_causal_streams({"gold": gold, "macro": macro},
                                    precedence=("macro", "gold")))
    assert [row.source for row in got] == ["macro", "gold"]


def test_late_macro_is_not_visible_at_historical_event_time():
    gold = [event("gold", 5, 10, 0), event("gold", 15, 20, 1)]
    macro = [event("macro", 2, 18, 0)]
    visible = list(merge_causal_streams({"macro": macro, "gold": gold},
                                        through_ns=16))
    assert [(row.source, row.event_at_ns) for row in visible] == [("gold", 5)]
    full = list(merge_causal_streams({"macro": macro, "gold": gold}))
    assert [row.source for row in full] == ["gold", "macro", "gold"]


def test_insertion_order_does_not_change_ties():
    gold = [event("gold", 2, 4, 1)]
    news = [event("news", 2, 4, 1)]
    def merge(d):
        return [e.source for e in merge_causal_streams(d)]
    assert merge({"news": news, "gold": gold}) == merge({"gold": gold, "news": news})


def test_reject_out_of_order_availability_and_sequence():
    bad = [event("gold", 10, 11, 1), event("gold", 9, 10, 2)]
    with pytest.raises(ValueError, match="Out-of-order"):
        list(merge_causal_streams({"gold": bad}))
    bad = [event("gold", 10, 11, 1), event("gold", 11, 12, 1)]
    with pytest.raises(ValueError, match="Out-of-order"):
        list(merge_causal_streams({"gold": bad}))


def test_reject_source_drift():
    first = event("gold", 5, 10, 0)
    second = CausalEvent(source="gold", source_sha256="b" * 64,
                         kind="research_quote", event_at_ns=6,
                         available_at_ns=11, sequence=1, values=(2,))
    with pytest.raises(ValueError, match="source-drifted"):
        list(merge_causal_streams({"gold": [first, second]}))


@pytest.mark.parametrize("values", [(float("nan"),), (float("inf"),), (True,),
                                      (1, "2"), (), tuple(range(33))])
def test_bad_quotes_are_never_silently_zeroed(values):
    with pytest.raises(ValueError):
        event("gold", 5, 10, 0, values)


def test_timestamps_cannot_use_bools_or_knowledge_before_event():
    with pytest.raises(ValueError):
        event("gold", 8, 7, 0)
    with pytest.raises(ValueError):
        event("gold", True, 7, 0)


def test_bounded_inputs_and_wrong_named_stream_rejected():
    with pytest.raises(ValueError):
        list(merge_causal_streams({}))
    with pytest.raises(ValueError):
        list(merge_causal_streams({"gold": [event("news", 1, 2, 0)]}))
    with pytest.raises(ValueError):
        list(merge_causal_streams({"gold": []}, precedence=("gold", "gold")))


def test_deterministic_1000_synthetic_events():
    streams = {
        name: [event(name, i * 10, i * 10 + 1, i)
               for i in range(250)]
        for name in ("gold", "macro", "news", "external")
    }
    events = list(merge_causal_streams(streams))
    assert len(events) == 1000
    assert [x.available_at_ns for x in events] == sorted(x.available_at_ns for x in events)
    assert events[0].source == "external"


def test_tie_priority_beats_old_observation_period():
    # A 2024 economic period fetched at the 2026 gold close cannot leap
    # ahead of that gold candle only because its period is chronologically old.
    gold = [event("gold", 100, 200, 0)]
    fred = [event("fred", 10, 200, 0)]
    got = list(merge_causal_streams({"gold": gold, "fred": fred},
                                    precedence=("gold", "fred")))
    assert [e.source for e in got] == ["gold", "fred"]
