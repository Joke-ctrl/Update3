"""
Trading session engine: tags bars by session (Asian/London/New York) using
UTC hour boundaries, and computes each session's high/low/sweep status.
"""
from __future__ import annotations

from app.engine.types import Bar, SessionWindow

# UTC hour ranges (inclusive start, exclusive end). Approximate, standard
# retail-trading convention; DST shifts London/NY by an hour part of the
# year, which is an acceptable simplification for session bias tagging.
SESSION_HOURS_UTC = {
    "asian": (0, 8),
    "london": (7, 16),
    "new_york": (12, 21),
}


def session_for_hour(hour_utc: int) -> list[str]:
    """A given UTC hour can belong to more than one session (overlaps)."""
    return [name for name, (start, end) in SESSION_HOURS_UTC.items() if start <= hour_utc < end]


def compute_session_windows(bars: list[Bar]) -> dict[str, SessionWindow]:
    windows = {name: SessionWindow(name=name) for name in SESSION_HOURS_UTC}

    for bar in bars:
        for session_name in session_for_hour(bar.time.hour):
            w = windows[session_name]
            w.high = bar.high if w.high is None else max(w.high, bar.high)
            w.low = bar.low if w.low is None else min(w.low, bar.low)

    return windows


def london_ny_overlap_hours() -> tuple[int, int]:
    l_start, l_end = SESSION_HOURS_UTC["london"]
    ny_start, ny_end = SESSION_HOURS_UTC["new_york"]
    return max(l_start, ny_start), min(l_end, ny_end)
