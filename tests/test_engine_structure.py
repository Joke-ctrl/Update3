from datetime import datetime, timedelta, timezone

from app.engine.structure import detect_structure_events, find_swing_points, label_swings
from app.engine.types import Bar, StructureEventType


def _mk_bars(prices: list[tuple[float, float, float, float]]) -> list[Bar]:
    """prices: list of (open, high, low, close)"""
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(time=t0 + timedelta(minutes=i), open=o, high=h, low=l, close=c)
        for i, (o, h, l, c) in enumerate(prices)
    ]


def test_finds_swing_high_and_low():
    # Clear peak at index 3, clear trough at index 7
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 11, 10, 11),
            (11, 12, 11, 12),
            (12, 15, 12, 14),  # swing high
            (14, 14, 12, 12),
            (12, 12, 10, 10),
            (10, 10, 8, 8),
            (8, 8, 5, 6),  # swing low
            (6, 8, 6, 7),
            (7, 9, 7, 8),
        ]
    )
    swings = find_swing_points(bars, lookback=2)
    highs = [s.index for s in swings if s.kind.value == "high"]
    lows = [s.index for s in swings if s.kind.value == "low"]
    assert 3 in highs
    assert 7 in lows


def test_bullish_bos_after_uptrend():
    # Uptrend making higher highs; a bullish break should register as BOS
    # once a bearish->bullish trend is already established, otherwise the
    # first break is reported as BOS by definition (no prior trend).
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 11, 10, 11),
            (11, 13, 11, 12),  # swing high @ index 2 (price 13)
            (12, 12, 10, 10),
            (10, 10, 8, 9),  # swing low @ index 4 (price 8)
            (9, 12, 9, 11),
            (11, 14, 11, 13.5),  # breaks above 13 -> bullish event
            (13.5, 16, 13, 15),
        ]
    )
    events, trend = detect_structure_events(bars, lookback=1)
    assert any(e.direction == "bullish" for e in events)
    assert trend == "bullish"


def test_choch_on_reversal():
    # Establish a bullish trend, then break back down through a protected
    # low -> should register as CHoCH bearish.
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 11, 10, 11),
            (11, 13, 11, 12),  # swing high, index 2, price 13
            (12, 12, 10, 10),
            (10, 10, 8, 9),  # swing low, index 4, price 8
            (9, 12, 9, 11),
            (11, 14, 11, 13.5),  # break above 13 -> BOS bullish, trend=bullish
            (13.5, 14, 12, 12),
            (12, 12, 10, 10),
            (10, 10, 7, 7.5),  # swing low forms around here
            (7.5, 9, 7, 8),
            (8, 8, 6, 6.5),  # breaks below prior low -> CHoCH bearish
        ]
    )
    events, trend = detect_structure_events(bars, lookback=1)
    choch_events = [e for e in events if e.event_type == StructureEventType.CHOCH]
    assert len(choch_events) >= 1
    assert choch_events[0].direction == "bearish"


def test_label_swings_hh_hl_lh_ll():
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 12, 10, 11),  # swing high #1 (index1, price 12)
            (11, 11, 9, 9),
            (9, 9, 7, 8),  # swing low #1 (index3, price 7)
            (8, 15, 8, 14),  # swing high #2 (index4, price 15) -> HH
            (14, 14, 12, 12),
            (12, 12, 10, 11),  # swing low #2 (index6, price 10) -> HL
        ]
    )
    swings = find_swing_points(bars, lookback=1)
    labels = label_swings(swings)
    values = list(labels.values())
    assert "HH" in values or "HL" in values  # at least one relative label produced


def test_swing_is_not_visible_before_confirmation_bar():
    bars = _mk_bars([
        (10, 10, 9, 10),
        (10, 11, 10, 11),
        (11, 15, 11, 14),  # swing high at index 2
        (14, 14, 10, 10),
        (10, 12, 9, 11),   # confirmation arrives at index 3 for lookback=1
        (11, 13, 10, 12),
    ])
    swings = find_swing_points(bars, lookback=1)
    swing = next(s for s in swings if s.index == 2)
    assert swing.confirmed_at == 3
