"""
Deterministic market-structure engine.

Important invariant: a swing at index i is not visible to structure logic
until index i + lookback. This prevents look-ahead bias. BOS/CHoCH are close
confirmed and each protected swing can trigger at most one break.
"""
from __future__ import annotations

from app.engine.types import Bar, StructureEvent, StructureEventType, SwingPoint, SwingType


def find_swing_points(bars: list[Bar], lookback: int = 2) -> list[SwingPoint]:
    if lookback < 1 or len(bars) < 2 * lookback + 1:
        return []
    swings: list[SwingPoint] = []
    n = len(bars)
    for i in range(lookback, n - lookback):
        center = bars[i]
        left = bars[i - lookback:i]
        right = bars[i + 1:i + lookback + 1]
        if center.high > max(b.high for b in left) and center.high > max(b.high for b in right):
            swings.append(SwingPoint(i, center.time, center.high, SwingType.HIGH, i + lookback))
        if center.low < min(b.low for b in left) and center.low < min(b.low for b in right):
            swings.append(SwingPoint(i, center.time, center.low, SwingType.LOW, i + lookback))
    return sorted(swings, key=lambda s: (s.confirmed_at or s.index, s.index))


def label_swings(swings: list[SwingPoint]) -> dict[int, str]:
    labels: dict[int, str] = {}
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    for s in sorted(swings, key=lambda x: x.index):
        if s.kind == SwingType.HIGH:
            if last_high is not None:
                labels[s.index] = "HH" if s.price > last_high.price else "LH"
            last_high = s
        else:
            if last_low is not None:
                labels[s.index] = "HL" if s.price > last_low.price else "LL"
            last_low = s
    return labels


def detect_structure_events(
    bars: list[Bar], lookback: int = 2
) -> tuple[list[StructureEvent], str | None]:
    if len(bars) < 2 * lookback + 2:
        return [], None

    swings = find_swing_points(bars, lookback)
    by_confirmation: dict[int, list[SwingPoint]] = {}
    for s in swings:
        by_confirmation.setdefault(s.confirmed_at or s.index, []).append(s)

    events: list[StructureEvent] = []
    trend: str | None = None
    protected_high: SwingPoint | None = None
    protected_low: SwingPoint | None = None

    for i, bar in enumerate(bars):
        # Only now does the engine learn that the fractal existed.
        for s in by_confirmation.get(i, []):
            if s.kind == SwingType.HIGH:
                protected_high = s
            else:
                protected_low = s

        # One candle can technically cross both levels; choose the direction
        # from its close relative to the protected levels and never emit two
        # contradictory events from one bar.
        broke_high = protected_high is not None and bar.close > protected_high.price
        broke_low = protected_low is not None and bar.close < protected_low.price

        if broke_high and broke_low:
            if abs(bar.close - protected_high.price) >= abs(bar.close - protected_low.price):
                broke_low = False
            else:
                broke_high = False

        if broke_high:
            broken = protected_high
            event_type = StructureEventType.CHOCH if trend == "bearish" else StructureEventType.BOS
            events.append(StructureEvent(event_type, i, bar.time, bar.close, "bullish", broken))
            trend = "bullish"
            protected_high = None

        elif broke_low:
            broken = protected_low
            event_type = StructureEventType.CHOCH if trend == "bullish" else StructureEventType.BOS
            events.append(StructureEvent(event_type, i, bar.time, bar.close, "bearish", broken))
            trend = "bearish"
            protected_low = None

    return events, trend
