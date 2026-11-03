"""OANDA v20 historical candle adapter: bounded, read-only, no order endpoints.

Only GET to the hard-coded fxPractice host. This is neither broker tick replay,
account-specific fill reconstruction nor authorization to trade. Never persist
tokens in manifests or errors. Historical candles may differ from account prices.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import json
import math
import re
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

import pandas as pd

PRACTICE_URL = "https://api-fxpractice.oanda.com"
INSTRUMENT = re.compile(r"[A-Z]{3}_[A-Z]{3}\Z")
MAX_MINUTES = 5000
MAX_RESPONSE_BYTES = 5_000_000


class _RejectRedirects(HTTPRedirectHandler):
    """Never forward the practice bearer token to a redirected endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("OANDA redirects are forbidden")


def utc_timestamp(value: object) -> pd.Timestamp:
    try:
        time = pd.Timestamp(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid timezone-aware event/candle time") from exc
    if pd.isna(time) or time.tzinfo is None:
        raise ValueError("UTC event/candle time must have a timezone")
    return time.tz_convert("UTC")


def decimal_price(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Invalid candle price type")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid candle price") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError("Nonpositive or nonfinite candle price")
    # Decimal can be finite but overflow IEEE754 when converted to float.
    price = float(number)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Candle price cannot be represented as finite float")
    return price


@dataclass(frozen=True)
class ClosedCandle:
    instrument: str
    opened_at: pd.Timestamp
    bid_o: float
    bid_h: float
    bid_l: float
    bid_c: float
    ask_o: float
    ask_h: float
    ask_l: float
    ask_c: float
    volume: int

    @property
    def known_at(self) -> pd.Timestamp:
        # OANDA candle time denotes the OPEN, not the time of known OHLC.
        return self.opened_at + pd.Timedelta(minutes=1)

    @property
    def spread_close(self) -> float:
        return self.ask_c - self.bid_c


def parse_closed_m1(payload: object, instrument: str) -> tuple[ClosedCandle, ...]:
    """Normalize ONLY complete BA M1 candles in the order observed.

    No synthetic ticks, interpolation, last incomplete candle, or silent sorting.
    Missing minutes remain missing and are guarded by the robot layer.
    """
    if not INSTRUMENT.fullmatch(instrument):
        raise ValueError("Invalid OANDA instrument")
    if not isinstance(payload, dict) or type(payload.get("candles")) is not list:
        raise ValueError("Malformed OANDA candle document")
    if payload.get("instrument", instrument) != instrument:
        raise ValueError("OANDA instrument mismatch")
    # Offline files may predate explicit metadata, but a provider document
    # declaring H1/M5 must never silently be reinterpreted as closed M1.
    if payload.get("granularity", "M1") != "M1":
        raise ValueError("OANDA candle granularity must be M1")
    if payload.get("price", "BA") != "BA":
        raise ValueError("OANDA candle price type must be BID/ASK")
    if len(payload["candles"]) > MAX_MINUTES:
        raise ValueError("OANDA M1 candle count exceeds bounded window")
    result: list[ClosedCandle] = []
    for raw in payload["candles"]:
        if not isinstance(raw, dict) or raw.get("complete") is not True:
            raise ValueError("Incomplete or malformed OANDA candle")
        at = utc_timestamp(raw.get("time"))
        if at != at.floor("min"):
            raise ValueError("OANDA M1 candle timestamp must align to UTC minute")
        def component(side: str) -> tuple[float, float, float, float]:
            val = raw.get(side)
            if not isinstance(val, dict) or set(("o", "h", "l", "c")) - set(val):
                raise ValueError("OANDA BID/ASK fields missing")
            values = tuple(decimal_price(val[k]) for k in ("o", "h", "l", "c"))
            o, h, low, c = values
            if low > min(o, c) or h < max(o, c) or low > h:
                raise ValueError("Invalid OANDA OHLC geometry")
            return values
        bid, ask = component("bid"), component("ask")
        # The high/low are separately aggregated but must still obey
        # ASK >= BID because OANDA BA quotes are pointwise non-crossed.
        if any(a < b for a, b in zip(ask, bid)):
            raise ValueError("ASK below BID in OANDA M1 bar")
        vol = raw.get("volume")
        if type(vol) is not int or vol < 0:
            raise ValueError("Invalid OANDA candle volume")
        if result and at <= result[-1].opened_at:
            raise ValueError("Unsorted/duplicate OANDA candle timestamps")
        result.append(ClosedCandle(instrument, at, *bid, *ask, vol))
    if not result:
        raise ValueError("Empty OANDA candle window")
    return tuple(result)


def fetch_practice_m1(instrument: str, start: object, end: object, *,
                      bearer_token: str, opener=None) -> tuple[ClosedCandle, ...]:
    """A single bounded BA historical request; no order/trade/account endpoint.

    Large windows must be partitioned upstream. No account-specific spread
    execution claims. Inject opener to test without any network/credentials.
    """
    if not INSTRUMENT.fullmatch(instrument):
        raise ValueError("Invalid instrument")
    start, end = utc_timestamp(start), utc_timestamp(end)
    if start != start.floor("min") or end != end.floor("min"):
        raise ValueError("OANDA M1 request boundaries must align to UTC minutes")
    minutes = (end - start) / pd.Timedelta(minutes=1)
    if not 0 < minutes <= MAX_MINUTES:
        raise ValueError("Request must cover 1..5000 M1 minutes")
    if not isinstance(bearer_token, str) or not bearer_token.strip():
        raise ValueError("OANDA practice bearer token unavailable")
    query = urlencode({
        "granularity": "M1", "price": "BA", "smooth": "false",
        "from": start.isoformat(), "to": end.isoformat(),
    })
    url = f"{PRACTICE_URL}/v3/instruments/{instrument}/candles?{query}"
    request = Request(url, headers={
        "Authorization": "Bearer " + bearer_token,
        "Accept": "application/json",
    }, method="GET")
    try:
        response = (opener or build_opener(_RejectRedirects()).open)(request, timeout=20)
        with response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("OANDA response exceeds bounded payload")
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("OANDA practice candle request rejected") from None
    except Exception:
        # Do not disclose token-bearing request headers or provider error bodies.
        raise RuntimeError("OANDA practice request failed; no orders attempted") from None
    candles = parse_closed_m1(payload, instrument)
    if any(c.opened_at < start or c.known_at > end for c in candles):
        raise ValueError("Candle outside requested closed interval")
    return candles
