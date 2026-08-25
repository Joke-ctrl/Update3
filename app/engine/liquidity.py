"""
Liquidity pools and sweep detector without future-data leakage.

Equal highs/lows are built only from swings whose confirmation time has
already passed. A sweep must occur after the pool exists and must wick
through the level before closing back on the original side.
"""
from __future__ import annotations

from app.engine.structure import find_swing_points
from app.engine.types import Bar, LiquiditySweep, SwingType


def _cluster(prices: list[float], tolerance_pct: float) -> list[float]:
    levels: list[float] = []
    for p in sorted(prices):
        if not levels or abs(p - levels[-1]) / max(abs(levels[-1]), 1e-12) * 100 > tolerance_pct:
            levels.append(p)
    return levels


def find_equal_levels(
    bars: list[Bar], lookback: int = 2, tolerance_pct: float = 0.05
) -> dict[str, list[float]]:
    swings = find_swing_points(bars, lookback)
    return {
        "highs": _cluster([s.price for s in swings if s.kind == SwingType.HIGH], tolerance_pct),
        "lows": _cluster([s.price for s in swings if s.kind == SwingType.LOW], tolerance_pct),
    }


def detect_liquidity_sweeps(
    bars: list[Bar], lookback: int = 2, tolerance_pct: float = 0.05
) -> list[LiquiditySweep]:
    swings = find_swing_points(bars, lookback)
    confirmed_highs: list = []
    confirmed_lows: list = []
    sweeps: list[LiquiditySweep] = []

    for i, bar in enumerate(bars):
        for s in swings:
            if s.confirmed_at == i:
                (confirmed_highs if s.kind == SwingType.HIGH else confirmed_lows).append(s)

        high_levels = _cluster([s.price for s in confirmed_highs], tolerance_pct)
        low_levels = _cluster([s.price for s in confirmed_lows], tolerance_pct)

        for level in high_levels:
            prior = [s for s in confirmed_highs if s.index < i and abs(s.price-level) / max(abs(level),1e-12)*100 <= tolerance_pct]
            if len(prior) >= 2 and bar.high > level and bar.close < level:
                nearest = min(prior, key=lambda s: abs(s.price-level))
                sweeps.append(LiquiditySweep(i, bar.time, "buy_side", level, nearest.index))

        for level in low_levels:
            prior = [s for s in confirmed_lows if s.index < i and abs(s.price-level) / max(abs(level),1e-12)*100 <= tolerance_pct]
            if len(prior) >= 2 and bar.low < level and bar.close > level:
                nearest = min(prior, key=lambda s: abs(s.price-level))
                sweeps.append(LiquiditySweep(i, bar.time, "sell_side", level, nearest.index))
    return sweeps
