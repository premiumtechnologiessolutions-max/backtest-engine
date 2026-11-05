"""Optional real NautilusTrader runtime on an invented bounded fixture only.

The adapter instantiates the installed vendor engine and records its native
order fills. It never reads user data, starts a shell, or fetches network data.
Vendor bar fills/fees are not our canonical XAUUSD execution/cost contract.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json

import numpy as np
import pandas as pd

PINNED_NAUTILUS_VERSION = '1.221.0'


class NautilusUnavailable(RuntimeError):
    """The pinned optional vendor runtime is absent or incompatible."""


def _validate(bars, seed):
    if type(bars) is not int or not 40 <= bars <= 2000:
        raise ValueError('Synthetic Nautilus fixture requires 40..2000 bars')
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('Synthetic fixture seed must be an unsigned 32-bit integer')


def _fixture(bars, seed):
    _validate(bars, seed)
    rng = np.random.default_rng(seed)
    # Invented, repeatable FX-like values. No historical or live observations.
    close = 1.1 + np.cumsum(rng.normal(0., .00005, bars))
    opened = np.r_[1.1, close[:-1]]
    bid = pd.DataFrame({
        'open': opened, 'high': np.maximum(opened, close) + .00003,
        'low': np.minimum(opened, close) - .00003, 'close': close,
        'volume': np.full(bars, 1_000_000.),
    }, index=pd.date_range('2020-01-06T00:01:00Z', periods=bars, freq='min'))
    bid.index.name = 'timestamp'
    for column in ('open', 'high', 'low', 'close'):
        bid[column] = bid[column].round(5)
    ask = bid.copy()
    for column in ('open', 'high', 'low', 'close'):
        ask[column] = (ask[column] + .0001).round(5)
    return bid, ask


def run_nautilus_synthetic(bars=240, seed=0) -> dict:
    """Run actual native orders against invented BID/ASK M1 bars.

    The fixed strategy enters once each 20 bars and closes 10 bars later.
    This verifies vendor integration, not an alpha, broker fill, or parity.
    """
    _validate(bars, seed)
    if importlib.util.find_spec('nautilus_trader') is None:
        raise NautilusUnavailable('Install the optional nautilus extra to run this adapter')
    version = importlib.metadata.version('nautilus_trader')
    if version != PINNED_NAUTILUS_VERSION:
        raise NautilusUnavailable(f'Requires nautilus_trader=={PINNED_NAUTILUS_VERSION}; found {version}')
    from nautilus_trader.backtest.config import BacktestEngineConfig
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import LoggingConfig
    from nautilus_trader.config import StrategyConfig
    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.data import BarType
    from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TimeInForce
    from nautilus_trader.model.identifiers import TraderId, Venue
    from nautilus_trader.model.objects import Money
    from nautilus_trader.persistence.wranglers import BarDataWrangler
    from nautilus_trader.test_kit.providers import TestInstrumentProvider
    from nautilus_trader.trading.strategy import Strategy

    venue = Venue('SIM')
    instrument = TestInstrumentProvider.default_fx_ccy('EUR/USD', venue)
    bid_type = BarType.from_str('EUR/USD.SIM-1-MINUTE-BID-EXTERNAL')
    ask_type = BarType.from_str('EUR/USD.SIM-1-MINUTE-ASK-EXTERNAL')
    bid, ask = _fixture(bars, seed)
    fixture_payload = {
        'timestamps_ns': [int(x) for x in bid.index.astype('int64')],
        'bid': bid.to_numpy().tolist(), 'ask': ask.to_numpy().tolist(),
    }
    fixture_digest = hashlib.sha256(json.dumps(
        fixture_payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    class SyntheticLifecycle(Strategy):
        def __init__(self):
            super().__init__(StrategyConfig())
            self.seen = 0
            self.native_fills = []
            self.closed_positions = 0
            self.rejected = 0

        def on_start(self):
            self.subscribe_bars(bid_type)

        def on_bar(self, bar):
            self.seen += 1
            # Wait for the first complete BID/ASK pair before entering.
            if self.seen % 20 == 2 and self.seen <= bars - 10:
                order = self.order_factory.market(
                    instrument_id=instrument.id, order_side=OrderSide.BUY,
                    quantity=instrument.make_qty(1_000), time_in_force=TimeInForce.GTC,
                )
                self.submit_order(order)
            elif self.seen % 20 == 12:
                self.close_all_positions(instrument.id)

        def on_order_filled(self, event):
            self.native_fills.append({
                'ts_event': int(event.ts_event), 'side': str(event.order_side),
                'quantity': str(event.last_qty), 'price': str(event.last_px),
                'commission': str(event.commission),
            })

        def on_position_closed(self, event):
            self.closed_positions += 1

        def on_order_rejected(self, event):
            self.rejected += 1

        def on_order_denied(self, event):
            self.rejected += 1

        def on_stop(self):
            self.cancel_all_orders(instrument.id)
            self.close_all_positions(instrument.id)
            self.unsubscribe_bars(bid_type)

    engine = BacktestEngine(config=BacktestEngineConfig(
        trader_id=TraderId('NRFXLAB-001'),
        logging=LoggingConfig(bypass_logging=True),
    ))
    try:
        engine.add_venue(venue=venue, oms_type=OmsType.HEDGING,
                         account_type=AccountType.MARGIN, base_currency=USD,
                         starting_balances=[Money(100_000, USD)], bar_execution=True)
        engine.add_instrument(instrument)
        engine.add_data(BarDataWrangler(bid_type, instrument).process(bid))
        engine.add_data(BarDataWrangler(ask_type, instrument).process(ask))
        strategy = SyntheticLifecycle()
        engine.add_strategy(strategy)
        engine.run()
        fills_report = engine.trader.generate_order_fills_report()
        positions_report = engine.trader.generate_positions_report()
        result = {
            'schema': 'NRFX_NAUTILUS_SYNTHETIC_RUNTIME_V1',
            'engine': 'nautilus_trader', 'engine_version': version,
            'runtime_executed': True, 'fixture': 'INVENTED_EURUSD_M1_BIDASK',
            'bars_per_side': bars, 'seed': seed, 'fixture_sha256': fixture_digest,
            'bars_observed_by_strategy': strategy.seen,
            'orders_count': len(engine.cache.orders()),
            'fills_count': len(strategy.native_fills),
            'native_fill_report_rows': len(fills_report),
            'native_position_report_rows': len(positions_report),
            'closed_positions_count': strategy.closed_positions,
            'rejected_or_denied_orders': strategy.rejected,
            'native_fills': strategy.native_fills,
            'cost_model': 'VENDOR_DEFAULT_FX_FIXTURE_FEES_NOT_CANONICAL_XAUUSD',
            'canonical_execution_parity_verified': False,
            'market_data_accessed': False, 'network_requested': False,
            'broker_orders_sent': False, 'profitability_claimed': False,
        }
        # Exclude UUIDs, wall-clock runtime and vendor logging from reproducible evidence.
        result['deterministic_sha256'] = hashlib.sha256(json.dumps(
            result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return result
    finally:
        engine.dispose()
