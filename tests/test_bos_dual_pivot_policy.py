import math

import pandas as pd

from norisk_quant.bos_fib import BosFibSettings, bos_fib_limit_orders


def _sample(n=450):
    ix = pd.date_range("2024-01-02T00:00:00Z", periods=n, freq="min")
    price = [100 + 0.075 * i + 1.7 * math.sin(i * 0.26) for i in range(n)]
    return pd.DataFrame({
        "o": price, "h": [x + .14 for x in price],
        "l": [x - .14 for x in price], "c": price,
    }, index=ix)


def test_ignore_ambiguous_double_pivot_is_causal_optional_version():
    market = _sample()
    j = 210
    # One outside M1 candle qualifies as both a pivot high and a pivot low.
    market.loc[market.index[j], "h"] = (
        max(market["h"].iloc[j-3:j+4]) + 15.
    )
    market.loc[market.index[j], "l"] = (
        min(market["l"].iloc[j-3:j+4]) - 15.
    )
    cfg = BosFibSettings(ignore_ambiguous_dual_pivots=True)
    orders = bos_fib_limit_orders(market, settings=cfg)
    assert orders
    first = orders[0]
    # A future cutoff may not rewrite an earlier BOS signal.
    prefix = market.loc[market.index < first.placed_at]
    assert bos_fib_limit_orders(prefix, settings=cfg)[0] == first
    # Keep archived 3,800-trade replay consistent by default.
    assert BosFibSettings().ignore_ambiguous_dual_pivots is False
