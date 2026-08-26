"""
Ensures `market_bars` has enough recent data for a (symbol, timeframe)
before the analysis pipeline reads it, backfilling from Twelve Data via
the existing fetch_twelve_data_bars() when it doesn't.

This does not replace the MT5 EA feed in app/api/routes/mt5.py -- either
path (or both) can populate the same table. They can never collide: bars
are deduped by the same (symbol, timeframe, bar_time) unique constraint
/mt5/ingest already relies on, so whichever feed writes a given bar
first "wins" and the other is a no-op skip.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import MarketBar
# _float is reused as-is from the Twelve Data adapter rather than
# duplicating a third float-parsing helper -- it's small, already
# covered by tests/test_market_data_providers.py, and stable.
from app.services.market_data_providers import _float, fetch_twelve_data_bars

# MT5-style timeframe code -> Twelve Data `interval` query param. Only
# timeframes listed here can be auto-backfilled; an unmapped timeframe
# is left alone and falls through to the caller's existing
# "insufficient bars" 422, unchanged.
_TD_INTERVALS: dict[str, str] = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
    "W1": "1week",
}

# How old the latest stored bar is allowed to be before it's treated as
# stale and a fetch is attempted anyway, even if the row *count* already
# meets the minimum. Deliberately generous: FX/metals bars really are
# closed over the weekend, so a same-week gap is expected, not broken.
# An unnecessary fetch attempt here is cheap and harmless -- any bar
# Twelve Data returns that's already stored is simply skipped by the
# unique constraint below -- so this errs toward re-checking rather than
# silently analyzing stale data.
_DEFAULT_STALE_AFTER = timedelta(hours=24)
_STALE_AFTER_OVERRIDES: dict[str, timedelta] = {
    "D1": timedelta(days=5),
    "W1": timedelta(days=10),
}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def upsert_market_bars(
    db: Session,
    symbol: str,
    timeframe: str,
    bars: list[dict],
    spread: float = 0.0,
) -> tuple[int, int]:
    """Insert OHLC bars into market_bars, deduped by the same
    (symbol, timeframe, bar_time) unique constraint /mt5/ingest uses.
    Each item in `bars` is a dict with time/open/high/low/close/volume
    keys (already typed: datetime + floats). Returns (stored, skipped).

    A bar failing the basic OHLC sanity check (high/low must contain
    open/close) is skipped rather than raising -- unlike /mt5/ingest,
    this ingests from a third-party provider as a transparent backfill,
    so one malformed upstream row should not fail the whole analysis
    request.
    """
    stored = 0
    skipped = 0

    for bar in bars:
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        if not (h >= max(o, c) and l <= min(o, c) and h >= l):
            skipped += 1
            continue

        bar_time = bar["time"]
        exists = db.execute(
            select(MarketBar).where(
                MarketBar.symbol == symbol,
                MarketBar.timeframe == timeframe,
                MarketBar.bar_time == bar_time,
            )
        ).scalar_one_or_none()

        if exists:
            skipped += 1
            continue

        db.add(
            MarketBar(
                symbol=symbol,
                timeframe=timeframe,
                bar_time=bar_time,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=bar.get("volume", 0.0),
                spread=spread,
            )
        )
        stored += 1

    db.commit()
    return stored, skipped


def _parse_twelve_data_bars(raw_bars: list[dict]) -> list[dict]:
    """Twelve Data time_series `values[]` items -> the dict shape
    upsert_market_bars() expects. Rows with an unparseable timestamp or
    OHLC value are dropped rather than raising, for the same reason
    upsert_market_bars() skips instead of raising.
    """
    parsed: list[dict] = []

    for item in raw_bars:
        raw_time = item.get("datetime")
        if not raw_time:
            continue
        try:
            bar_time = datetime.fromisoformat(str(raw_time))
        except ValueError:
            continue
        if bar_time.tzinfo is None:
            # Twelve Data returns naive timestamps for 24-hour FX/metals
            # instruments in UTC; align with the UTC-aware bar_time
            # values /mt5/ingest already writes so both feeds compare
            # correctly (e.g. in the freshness check below).
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        o, h, l, c = (
            _float(item.get("open")),
            _float(item.get("high")),
            _float(item.get("low")),
            _float(item.get("close")),
        )
        if None in (o, h, l, c):
            continue

        parsed.append(
            {
                "time": bar_time,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": _float(item.get("volume")) or 0.0,
            }
        )

    return parsed


async def ensure_recent_bars(
    db: Session,
    symbol: str,
    timeframe: str,
    min_bars: int,
    outputsize: int,
) -> None:
    """Guarantee `market_bars` has at least `min_bars` reasonably recent
    rows for (symbol, timeframe) before the caller reads them, backfilling
    from Twelve Data via the existing fetch_twelve_data_bars() when it
    doesn't. No-ops -- leaving the caller's existing insufficient-bars
    422 to fire exactly as before -- when: enough recent rows already
    exist, no TWELVE_DATA_API_KEY is configured (fetch_twelve_data_bars()
    itself returns [] in that case), Twelve Data returns nothing usable,
    or `timeframe` has no known Twelve Data interval mapping.
    """
    count, latest = db.execute(
        select(func.count(), func.max(MarketBar.bar_time)).where(
            MarketBar.symbol == symbol,
            MarketBar.timeframe == timeframe,
        )
    ).one()

    stale_after = _STALE_AFTER_OVERRIDES.get(timeframe, _DEFAULT_STALE_AFTER)
    is_fresh = latest is not None and (datetime.now(timezone.utc) - _aware(latest)) <= stale_after

    if count >= min_bars and is_fresh:
        return

    interval = _TD_INTERVALS.get(timeframe)
    if interval is None:
        return

    raw_bars = await fetch_twelve_data_bars(symbol, interval=interval, outputsize=outputsize)
    if not raw_bars:
        return

    upsert_market_bars(
        db,
        symbol=symbol,
        timeframe=timeframe,
        bars=_parse_twelve_data_bars(raw_bars),
    )
