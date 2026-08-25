"""
Order-block detector tied to actual displacement-backed BOS/CHoCH events.

For a bullish event, the detector searches backwards from the structural
break for the last bearish candle before the displacement leg. The mirror
rule is used for bearish events. Mitigation is only evaluated after the OB
has formed, and the break candle itself is excluded.
"""
from __future__ import annotations

from app.engine.displacement import is_displacement_candle
from app.engine.structure import detect_structure_events
from app.engine.types import Bar, OrderBlock


def _bearish(b: Bar) -> bool:
    return b.close < b.open


def _bullish(b: Bar) -> bool:
    return b.close > b.open


def detect_order_blocks(
    bars: list[Bar], lookback: int = 2, search_window: int = 10
) -> list[OrderBlock]:
    events, _ = detect_structure_events(bars, lookback)
    result: list[OrderBlock] = []

    for event in events:
        if not is_displacement_candle(bars, event.index):
            continue
        start = max(0, event.index - search_window)
        for j in range(event.index - 1, start - 1, -1):
            candidate = bars[j]
            valid = _bearish(candidate) if event.direction == "bullish" else _bullish(candidate)
            if not valid:
                continue
            ob = OrderBlock(
                index=j,
                time=candidate.time,
                direction=event.direction,
                top=candidate.high,
                bottom=candidate.low,
                break_index=event.index,
            )
            # Only bars after the break can mitigate the newly formed OB.
            for k in range(event.index + 1, len(bars)):
                bar = bars[k]
                if bar.low <= ob.top and bar.high >= ob.bottom:
                    ob.mitigated, ob.mitigation_index = True, k
                    break
            result.append(ob)
            break
    return result
