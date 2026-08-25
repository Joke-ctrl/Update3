"""Market-data endpoints for the dashboard and chart layer."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.market_data import MarketBar
from app.models.user import User
from app.schemas.market_data import BarOut, InstrumentOut, QuoteOut
from app.services.instruments import canonical_symbol, instrument_payload
from app.services.market_data_providers import (
    fetch_twelve_data_quote,
    fetch_twelve_data_quotes,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get(
    "/instruments",
    response_model=list[InstrumentOut],
)
def instruments(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, object]]:
    """Return the canonical instruments supported by the app."""
    return instrument_payload()


@router.get(
    "/quotes",
    response_model=list[QuoteOut],
)
async def live_quotes(
    current_user: User = Depends(get_current_user),
) -> list[QuoteOut]:

    symbols = [
        "NAS100",
        "US30",
        "XAUUSD",
        "EURUSD",
    ]

    quotes = await fetch_twelve_data_quotes(symbols)

    return [
        QuoteOut(
            **{
                **quote.__dict__,
                "symbol": canonical_symbol(quote.symbol),
            }
        )
        for quote in quotes
    ]


@router.get(
    "/quotes/{symbol}",
    response_model=QuoteOut | None,
)
async def live_quote(
    symbol: str,
    current_user: User = Depends(get_current_user),
) -> QuoteOut | None:

    target = canonical_symbol(symbol)

    quote = await fetch_twelve_data_quote(target)

    if quote is None:
        return None

    return QuoteOut(
        **{
            **quote.__dict__,
            "symbol": target,
        }
    )


@router.get(
    "/bars/{symbol}",
    response_model=list[BarOut],
)
def chart_bars(
    symbol: str,
    timeframe: str = Query(
        "M15",
        min_length=1,
        max_length=10,
    ),
    limit: int = Query(
        200,
        ge=1,
        le=2000,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MarketBar]:

    target = canonical_symbol(symbol)

    rows = (
        db.execute(
            select(MarketBar)
            .where(
                MarketBar.symbol == target,
                MarketBar.timeframe == timeframe.upper(),
            )
            .order_by(MarketBar.bar_time.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    return list(reversed(rows))