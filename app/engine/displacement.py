"""
Displacement detection: identifies unusually large, momentum-driven
candles relative to recent volatility. Used to filter FVGs/order blocks
down to the ones formed by genuine institutional-style moves, not noise.
"""
from __future__ import annotations

from app.engine.types import Bar


def average_range(bars: list[Bar], end_index: int, window: int = 14) -> float:
    """Average high-low range over the `window` bars preceding end_index."""
    start = max(0, end_index - window)
    segment = bars[start:end_index]
    if not segment:
        return 0.0
    return sum(b.high - b.low for b in segment) / len(segment)


def is_displacement_candle(bars: list[Bar], index: int, window: int = 14, multiplier: float = 1.5) -> bool:
    """
    A candle is a displacement candle if its body is at least `multiplier`
    times the average range of the preceding `window` candles -- i.e. a
    genuinely oversized, momentum move rather than typical noise.
    """
    if index <= 0 or index >= len(bars):
        return False
    bar = bars[index]
    body = abs(bar.close - bar.open)
    avg_range = average_range(bars, index, window=window)
    if avg_range == 0:
        return False
    return body >= multiplier * avg_range
