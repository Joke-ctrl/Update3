"""
Economic calendar endpoints (see app/services/economic_calendar.py).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.economic_calendar import get_upcoming_events

router = APIRouter(prefix="/calendar", tags=["calendar"])


class EconomicEventOut(BaseModel):
    name: str
    currency: str
    impact: str
    event_time: str
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


@router.get("/upcoming", response_model=list[EconomicEventOut])
async def upcoming_events(
    hours_ahead: int = 24,
    current_user: User = Depends(get_current_user),
) -> list[EconomicEventOut]:
    events = await get_upcoming_events(hours_ahead=hours_ahead)
    return [
        EconomicEventOut(
            name=e.name,
            currency=e.currency,
            impact=e.impact,
            event_time=e.event_time.isoformat(),
            forecast=e.forecast,
            previous=e.previous,
            actual=e.actual,
        )
        for e in events
    ]
