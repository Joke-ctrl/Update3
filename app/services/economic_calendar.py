"""
Economic calendar integration.

Forex Factory has no official public API, and its own community explicitly
discourages raw scraping (see forexfactory.com/thread/1247273). Rather than
scrape against that, this uses JBlanked's free Calendar API
(jblanked.com/news/api/docs/calendar/), which aggregates Forex Factory,
MQL5, and FxStreet data behind a real, documented, key-authenticated
endpoint -- free to use, just requires signing up for a key.

Set CALENDAR_API_KEY in the environment to enable this. Without a key,
`get_upcoming_events()` returns an empty list and `is_blackout_window()`
returns False rather than fabricating events.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings

JBLANKED_BASE_URL = "https://www.jblanked.com/news/api"
FMP_CALENDAR_URL = "https://financialmodelingprep.com/stable/economic-calendar"

HIGH_IMPACT_LEVELS = {"high", "red", "3"}


@dataclass
class EconomicEvent:
    name: str
    currency: str
    impact: str
    event_time: datetime
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


async def get_upcoming_events(hours_ahead: int = 24) -> list[EconomicEvent]:
    settings = get_settings()
    api_key = getattr(settings, "CALENDAR_API_KEY", "")
    async with httpx.AsyncClient(timeout=10.0) as client:
        raw_events = None
        if api_key:
            try:
                response = await client.get(
                    f"{JBLANKED_BASE_URL}/calendar/",
                    headers={"Authorization": f"Api-Key {api_key}"},
                )
                response.raise_for_status()
                raw_events = response.json()
            except (httpx.HTTPError, ValueError):
                raw_events = None

        # Optional FMP fallback. It is only used when a key is configured and
        # the primary JBlanked feed is unavailable.
        if raw_events is None and getattr(settings, "FMP_API_KEY", ""):
            try:
                response = await client.get(
                    FMP_CALENDAR_URL,
                    params={"apikey": settings.FMP_API_KEY},
                )
                response.raise_for_status()
                raw_events = response.json()
            except (httpx.HTTPError, ValueError):
                raw_events = []

    if not isinstance(raw_events, list):
        return []

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)
    events: list[EconomicEvent] = []

    for item in raw_events if isinstance(raw_events, list) else []:
        try:
            raw_date = item.get("date") or item.get("eventDate")
            event_time = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        if not (now <= event_time <= cutoff):
            continue
        events.append(
            EconomicEvent(
                name=item.get("name") or item.get("event") or "Unknown event",
                currency=item.get("currency") or item.get("country") or "",
                impact=str(item.get("strength", item.get("impact", item.get("importance", "")))).lower(),
                event_time=event_time,
                forecast=item.get("forecast"),
                previous=item.get("previous"),
                actual=item.get("actual"),
            )
        )

    return events


async def is_blackout_window(
    currencies: list[str], minutes_before: int = 30, minutes_after: int = 30
) -> tuple[bool, EconomicEvent | None]:
    """
    Returns (in_blackout, triggering_event). A blackout is active if a
    high-impact event for one of the given currencies falls within
    [-minutes_before, +minutes_after] of now.
    """
    events = await get_upcoming_events(hours_ahead=max(1, minutes_after // 60 + 1))
    now = datetime.now(timezone.utc)

    for event in events:
        if event.impact not in HIGH_IMPACT_LEVELS:
            continue
        if event.currency.upper() not in {c.upper() for c in currencies}:
            continue
        window_start = event.event_time - timedelta(minutes=minutes_before)
        window_end = event.event_time + timedelta(minutes=minutes_after)
        if window_start <= now <= window_end:
            return True, event

    return False, None
