"""FAC024 synthetic-only, no original private market data or OOS claims."""
import pandas as pd
import pytest
from norisk_quant.spread_sweep import SpreadSweepSettings, spread_recovery_sweep_signals


def fixture_m1():
    start = pd.Timestamp('2024-01-08T12:00:00Z')
    rows = []
    for bar in range(14):
        o, h, l, c = (100., 101., 99., 100.)
        if bar == 12:
            o, h, l, c = (100., 100.8, 98., 99.5)
        for minute in range(15):
            spread = .8 if bar == 12 and minute == 0 else .4
            rows.append((start + pd.Timedelta(minutes=bar * 15 + minute),
                         o, h, l, c, o + spread, h + 1.0, l + .4, c + .4))
    return pd.DataFrame(rows, columns=['at','o','h','l','c','ao','ah','al','ac']).set_index('at')


def test_qualifying_signal_after_completed_sweep():
    sigs = spread_recovery_sweep_signals(fixture_m1())
    assert len(sigs) == 1
    assert sigs[0].confirmed_at == pd.Timestamp('2024-01-08T15:15:00Z')
    assert sigs[0].side == 1
    assert sigs[0].strategy == 'FAC024_M15_SPREAD_RECOVERY_SWEEP_FROZEN'


def test_no_future_bar_lookahead():
    before = spread_recovery_sweep_signals(fixture_m1())
    data = fixture_m1()
    data.loc[data.index[-15:], ['o','h','l','c','ao','ah','al','ac']] = [100.,108.,99.,100.,100.4,109.,99.4,100.4]
    assert spread_recovery_sweep_signals(data)[0] == before[0]


def test_no_initial_spread_expansion():
    data = fixture_m1()
    at = pd.Timestamp('2024-01-08T15:00:00Z')
    data.loc[at, 'ao'] = 100.4
    assert not spread_recovery_sweep_signals(data)


def test_no_spread_recovery_at_close():
    data = fixture_m1()
    at = pd.Timestamp('2024-01-08T15:14:00Z')
    data.loc[at, 'ac'] = 100.4
    assert not spread_recovery_sweep_signals(data)


def test_missing_baseline_minute_fails_closed():
    data = fixture_m1().drop(pd.Timestamp('2024-01-08T14:40:00Z'))
    assert not spread_recovery_sweep_signals(data)


def test_missing_sweep_minute_fails_closed():
    data = fixture_m1().drop(pd.Timestamp('2024-01-08T15:08:00Z'))
    assert not spread_recovery_sweep_signals(data)


def test_crossed_bid_ask_fails_closed():
    data = fixture_m1()
    data.loc[data.index[0], 'ao'] = 99.9
    with pytest.raises(ValueError, match='crossed'):
        spread_recovery_sweep_signals(data)


def test_non_utc_fails_closed():
    data = fixture_m1()
    data.index = data.index.tz_convert('Europe/London')
    with pytest.raises(ValueError, match='UTC'):
        spread_recovery_sweep_signals(data)


@pytest.mark.parametrize('kwargs', [
    {'lookback_m15': 11}, {'lookback_m15': True},
    {'spread_baseline_minutes': 30},
    {'initial_spread_multiple': 1.4},
    {'recovered_spread_multiple': 1.2},
    {'penetration_usd': .3},
    {'reward_risk': float('nan')},
])
def test_frozen_parameters_cannot_be_changed(kwargs):
    with pytest.raises(ValueError, match='frozen'):
        SpreadSweepSettings(**kwargs)


@pytest.mark.parametrize(('column', 'bad_value'), [
    ('h', 99.0), ('l', 100.2), ('ah', 100.1), ('al', 100.5),
])
def test_impossible_bid_ask_envelope_rejected_before_signal_generation(column, bad_value):
    data = fixture_m1()
    # Neutral first bar keeps every BID <= ASK comparison valid, so this
    # specifically exercises the envelope gate rather than crossed quotes.
    data.loc[data.index[0], ['o', 'h', 'l', 'c', 'ao', 'ah', 'al', 'ac']] = [
        100., 100., 100., 100., 100.4, 100.4, 100.4, 100.4,
    ]
    data.loc[data.index[0], column] = bad_value
    with pytest.raises(ValueError, match='bar geometry'):
        spread_recovery_sweep_signals(data)


def test_complex_quote_rejected_without_silent_imaginary_loss():
    data = fixture_m1()
    data['o'] = [100 + 1j] * len(data)
    with pytest.raises(ValueError, match='real numeric'):
        spread_recovery_sweep_signals(data)


def test_duplicate_quote_columns_rejected_before_numeric_cast():
    data = fixture_m1()
    data = pd.concat([data, data[['o']]], axis=1)
    with pytest.raises(ValueError, match='unique quote column'):
        spread_recovery_sweep_signals(data)
