"""
Three-candle Fair Value Gap detector with displacement filtering and
full-fill tracking. A gap is not marked filled merely because price touches
its edge; it is filled when price traverses the complete gap.
"""
from __future__ import annotations

from app.engine.displacement import is_displacement_candle
from app.engine.types import Bar, FairValueGap


def detect_fair_value_gaps(
    bars: list[Bar],
    require_displacement: bool = True,
    min_gap_size: float = 0.0,
) -> list[FairValueGap]:
    gaps: list[FairValueGap] = []
    for i in range(1, len(bars) - 1):
        prev_bar, mid, next_bar = bars[i - 1], bars[i], bars[i + 1]
        if require_displacement and not is_displacement_candle(bars, i):
            continue
        if next_bar.low > prev_bar.high and next_bar.low - prev_bar.high >= min_gap_size:
            gaps.append(FairValueGap(i, mid.time, "bullish", next_bar.low, prev_bar.high))
        elif next_bar.high < prev_bar.low and prev_bar.low - next_bar.high >= min_gap_size:
            gaps.append(FairValueGap(i, mid.time, "bearish", prev_bar.low, next_bar.high))

    for gap in gaps:
        for j in range(gap.index + 2, len(bars)):
            bar = bars[j]
            if gap.direction == "bullish" and bar.low <= gap.bottom:
                gap.filled, gap.fill_index = True, j
                break
            if gap.direction == "bearish" and bar.high >= gap.top:
                gap.filled, gap.fill_index = True, j
                break
    return gaps
