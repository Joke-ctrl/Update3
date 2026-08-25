"""
Premium/discount and dealing-range calculations.

The primary range is the most recently completed swing high/low pair rather
than an arbitrary global max/min. The midpoint is equilibrium; long setups
prefer discount and short setups prefer premium.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.engine.structure import find_swing_points
from app.engine.types import Bar, SwingType


@dataclass(frozen=True)
class DealingRange:
    range_high: float
    range_low: float
    equilibrium: float
    high_index: int | None = None
    low_index: int | None = None

    def zone_for(self, price: float) -> str:
        if price > self.equilibrium:
            return "premium"
        if price < self.equilibrium:
            return "discount"
        return "equilibrium"


def compute_dealing_range(
    bars: list[Bar], lookback: int = 2, window: int = 50
) -> DealingRange | None:
    recent = bars[-window:] if len(bars) > window else bars
    swings = find_swing_points(recent, lookback)
    highs = [s for s in swings if s.kind == SwingType.HIGH]
    lows = [s for s in swings if s.kind == SwingType.LOW]
    if not highs or not lows:
        return None

    # Prefer the latest high/low pair that forms a completed range. If they
    # are out of chronological order, the latest member of the pair still
    # defines the current dealing range.
    high = highs[-1]
    low = lows[-1]
    return DealingRange(
        range_high=high.price,
        range_low=low.price,
        equilibrium=(high.price + low.price) / 2,
        high_index=high.index,
        low_index=low.index,
    )
