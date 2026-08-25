"""
SMT divergence detector using aligned swing extrema.

For an inverse pair such as XAUUSD/DXY:
* bullish SMT: primary makes a lower low while the correlated market fails
  to make the corresponding higher high;
* bearish SMT: primary makes a higher high while the correlated market fails
  to make the corresponding lower low.

The comparison uses swings nearest in time, never future bars beyond the
primary swing being evaluated.
"""
from __future__ import annotations

from app.engine.structure import find_swing_points
from app.engine.types import Bar, SMTDivergence, SwingType


def detect_smt_divergence(
    primary_bars: list[Bar],
    correlated_bars: list[Bar],
    lookback: int = 2,
    inverse_correlation: bool = True,
) -> list[SMTDivergence]:
    p = find_swing_points(primary_bars, lookback)
    c = find_swing_points(correlated_bars, lookback)
    if len(p) < 2 or len(c) < 2:
        return []

    def nearest_by_time(swings, idx, max_index):
        eligible = [s for s in swings if s.index <= max_index]
        return min(eligible, key=lambda s: abs(s.index - idx), default=None)

    out: list[SMTDivergence] = []
    p_lows = [s for s in p if s.kind == SwingType.LOW]
    p_highs = [s for s in p if s.kind == SwingType.HIGH]
    c_lows = [s for s in c if s.kind == SwingType.LOW]
    c_highs = [s for s in c if s.kind == SwingType.HIGH]

    if len(p_lows) >= 2:
        a, b = p_lows[-2:]
        if b.price < a.price:
            if inverse_correlation:
                # Gold LL should be accompanied by DXY HH.
                ca = nearest_by_time(c_highs, a.index, b.index)
                cb = nearest_by_time(c_highs, b.index, b.index)
                if ca and cb and cb.price <= ca.price:
                    out.append(SMTDivergence(
                        b.index, b.time, "bullish",
                        "Primary made a lower low while the inverse instrument failed to make a higher high."
                    ))
            else:
                ca = nearest_by_time(c_lows, a.index, b.index)
                cb = nearest_by_time(c_lows, b.index, b.index)
                if ca and cb and cb.price >= ca.price:
                    out.append(SMTDivergence(
                        b.index, b.time, "bullish",
                        "Primary made a lower low while the correlated instrument failed to confirm with a lower low."
                    ))

    if len(p_highs) >= 2:
        a, b = p_highs[-2:]
        if b.price > a.price:
            if inverse_correlation:
                ca = nearest_by_time(c_lows, a.index, b.index)
                cb = nearest_by_time(c_lows, b.index, b.index)
                if ca and cb and cb.price >= ca.price:
                    out.append(SMTDivergence(
                        b.index, b.time, "bearish",
                        "Primary made a higher high while the inverse instrument failed to make a lower low."
                    ))
            else:
                ca = nearest_by_time(c_highs, a.index, b.index)
                cb = nearest_by_time(c_highs, b.index, b.index)
                if ca and cb and cb.price <= ca.price:
                    out.append(SMTDivergence(
                        b.index, b.time, "bearish",
                        "Primary made a higher high while the correlated instrument failed to confirm with a higher high."
                    ))
    return out
