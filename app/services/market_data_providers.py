"""
Market-data adapters used by MarketKill3r.

Twelve Data is used for live quotes and historical/intraday bars.
API keys belong in environment variables, never in source control.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings


TWELVE_DATA_QUOTE_URL = "https://api.twelvedata.com/quote"
TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"


@dataclass
class MarketQuote:
    symbol: str
    bid: float | None
    ask: float | None
    price: float | None
    timestamp: datetime
    source: str


def _normalise_symbol(symbol: str) -> str:
    return (
        symbol.replace("/", "")
        .replace("_", "")
        .upper()
        .strip()
    )


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def fetch_twelve_data_quote(
    symbol: str,
) -> MarketQuote | None:
    """Fetch one live quote from Twelve Data."""

    settings = get_settings()

    if not settings.TWELVE_DATA_API_KEY:
        return None

    symbol = _normalise_symbol(symbol)

    params = {
        "symbol": symbol,
        "apikey": settings.TWELVE_DATA_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                TWELVE_DATA_QUOTE_URL,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

    except (httpx.HTTPError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    if payload.get("status") == "error":
        return None

    price = _float(payload.get("close"))

    if price is None:
        price = _float(payload.get("price"))

    if price is None:
        return None

    timestamp = datetime.now(timezone.utc)

    raw_timestamp = payload.get("timestamp")

    if raw_timestamp is not None:
        try:
            timestamp = datetime.fromtimestamp(
                float(raw_timestamp),
                tz=timezone.utc,
            )
        except (TypeError, ValueError, OverflowError):
            pass

    return MarketQuote(
        symbol=symbol,
        bid=_float(payload.get("bid")),
        ask=_float(payload.get("ask")),
        price=price,
        timestamp=timestamp,
        source="twelvedata.com",
    )


async def fetch_twelve_data_quotes(
    symbols: list[str],
) -> list[MarketQuote]:
    """Fetch live quotes for MarketKill3r instruments."""

    quotes: list[MarketQuote] = []

    for symbol in symbols:
        quote = await fetch_twelve_data_quote(symbol)

        if quote is not None:
            quotes.append(quote)

    return quotes


async def fetch_twelve_data_bars(
    symbol: str,
    interval: str = "15min",
    outputsize: int = 200,
) -> list[dict[str, Any]]:
    """Fetch historical/intraday bars from Twelve Data."""

    settings = get_settings()

    if not settings.TWELVE_DATA_API_KEY:
        return []

    params = {
        "symbol": _normalise_symbol(symbol),
        "interval": interval,
        "outputsize": min(max(outputsize, 1), 5000),
        "apikey": settings.TWELVE_DATA_API_KEY,
        "format": "JSON",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                TWELVE_DATA_URL,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

    except (httpx.HTTPError, ValueError):
        return []

    values = (
        payload.get("values", [])
        if isinstance(payload, dict)
        else []
    )

    return [
        item
        for item in values
        if isinstance(item, dict)
    ]