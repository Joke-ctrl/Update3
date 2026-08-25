"""Schemas for market data queries and live quotes."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    timeframe: str
    bar_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class QuoteOut(BaseModel):
    symbol: str
    bid: float | None = None
    ask: float | None = None
    price: float | None = None
    timestamp: datetime
    source: str


class InstrumentOut(BaseModel):
    symbol: str
    name: str
    category: str
