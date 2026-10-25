"""H1 regime age gate must not read far-back stale hourly signals."""
import numpy as np
import pandas as pd
import pytest
from norisk_quant.h1_regime import H1RegimeSettings, filter_orders_h1
from norisk_quant.limit_engine import LimitOrder


def _quotes():
    ix = pd.date_range("2024-01-02T00:00:00Z", periods=3900, freq="min")
    px = 2000 + np.arange(len(ix)) * .04
    return pd.DataFrame({"o": px, "h": px + .2, "l": px - .2, "c": px}, index=ix)


def _order(at):
    return LimitOrder(
        placed_at=at, expires_at=at + pd.Timedelta(minutes=10),
        side=1, price=2000, stop=1990, target=2010,
    )


def test_h1_age_guard_rejects_weekend_stale_signal_but_preserves_baseline():
    data = _quotes()
    last_confirmed_hour = data.index[-1] + pd.Timedelta(minutes=1)
    weekend = last_confirmed_hour + pd.Timedelta(days=2)
    candidate = _order(weekend)
    # Historical no-age-limit runs remain reproducible by default.
    assert filter_orders_h1(data, [candidate]) == [candidate]
    # Explicit cutoff is a distinct, stricter experiment.
    assert filter_orders_h1(
        data, [candidate], cfg=H1RegimeSettings(max_regime_age_minutes=120)
    ) == []
    same_hour = _order(last_confirmed_hour)
    assert filter_orders_h1(
        data, [same_hour], cfg=H1RegimeSettings(max_regime_age_minutes=120)
    ) == [same_hour]


def test_reject_negative_h1_age_cutoff():
    with pytest.raises(ValueError, match="maximum age"):
        H1RegimeSettings(max_regime_age_minutes=-1)
