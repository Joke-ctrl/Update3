"""Canonical MarketKill3r instrument catalog and symbol aliases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    category: str
    aliases: tuple[str, ...] = ()


INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("NAS100", "Nasdaq 100", "Indices", ("NASDAQ", "NASDAQ100", "US100", "USTEC")),
    Instrument("US30", "Dow Jones 30", "Indices", ("DJ30", "DOW30", "DOWJONES", "US30USD")),
    Instrument("XAUUSD", "Gold / US Dollar", "Metals", ("XAU/USD", "GOLD")),
    Instrument("EURUSD", "Euro / US Dollar", "Forex", ("EUR/USD",)),
    Instrument("USDJPY", "US Dollar / Yen", "Forex", ("USD/JPY",)),
    Instrument("GBPUSD", "British Pound / US Dollar", "Forex", ("GBP/USD",)),
    Instrument("BTCUSD", "Bitcoin / US Dollar", "Crypto", ("BTC/USD", "BITCOIN")),
    Instrument("DXY", "US Dollar Index", "Index", ("USDINDEX", "USDX")),
)

_ALIAS_TO_SYMBOL = {
    alias.replace("/", "").replace("_", "").replace("-", "").upper(): item.symbol
    for item in INSTRUMENTS
    for alias in (item.symbol, *item.aliases)
}


def canonical_symbol(symbol: str) -> str:
    """Return the canonical MarketKill3r symbol for a user/provider alias."""
    key = symbol.replace("/", "").replace("_", "").replace("-", "").strip().upper()
    return _ALIAS_TO_SYMBOL.get(key, key)


def instrument_payload() -> list[dict[str, object]]:
    return [
        {"symbol": i.symbol, "name": i.name, "category": i.category}
        for i in INSTRUMENTS
    ]
