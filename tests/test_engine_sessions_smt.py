from datetime import datetime, timedelta, timezone

from app.engine.sessions import compute_session_windows, session_for_hour
from app.engine.smt import detect_smt_divergence
from app.engine.types import Bar


def _mk_bars_at_hours(hours: list[int]) -> list[Bar]:
    d = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(time=d.replace(hour=h), open=10, high=11, low=9, close=10)
        for h in hours
    ]


def test_session_for_hour_classification():
    assert "asian" in session_for_hour(2)
    assert "london" in session_for_hour(9)
    assert "new_york" in session_for_hour(14)
    # London/NY overlap hour
    assert "london" in session_for_hour(13) and "new_york" in session_for_hour(13)


def test_session_windows_track_high_low():
    bars = _mk_bars_at_hours([1, 2, 3])
    windows = compute_session_windows(bars)
    assert windows["asian"].high == 11
    assert windows["asian"].low == 9


def _mk_bars(prices):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(time=t0 + timedelta(minutes=i), open=o, high=h, low=l, close=c)
        for i, (o, h, l, c) in enumerate(prices)
    ]


def test_smt_bullish_divergence_inverse_pair():
    # XAUUSD makes a lower low; DXY (inverse) should make a higher low to
    # confirm. If DXY ALSO makes a lower low, that's bullish SMT divergence
    # for gold (DXY failing to rally on gold's weakness).
    gold = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 10, 7, 8),    # swing low #1 @ 7
            (8, 10, 8, 9),
            (9, 9, 8, 8.5),
            (8.5, 9, 5, 6),    # swing low #2 @ 5 (lower low)
            (6, 8, 6, 7),
        ]
    )
    dxy = _mk_bars(
        [
            (100, 101, 99, 100),
            (100, 101, 97, 98),   # context
            (98, 102, 98, 101),   # swing high #1 @ 102
            (99, 100, 98, 99),
            (99, 101, 99, 100),   # swing high #2 @ 101 (fails to make a higher high)
            (103, 103, 101, 102),
            (102, 103, 100, 101),
        ]
    )
    divs = detect_smt_divergence(gold, dxy, lookback=1, inverse_correlation=True)
    assert any(d.direction == "bullish" for d in divs)
