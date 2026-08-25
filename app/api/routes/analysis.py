"""
Versioned multi-timeframe analysis API.

The route is orchestration only:
- loads validated persisted market bars
- loads correlated-symbol bars for SMT
- fetches optional economic/news context
- calls the deterministic multi-timeframe SMC pipeline
- persists the auditable analysis/signal
- returns the complete Signal contract
"""

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.reasoning import generate_narrative
from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.engine.pipeline import analyze_multi_timeframe
from app.engine.types import Bar
from app.models.analysis import AnalysisRun
from app.models.market_data import MarketBar
from app.models.signal import Signal, SignalDirection
from app.models.user import User
from app.schemas.signal import AnalysisRequest, AnalysisRunOut, SignalOut
from app.services.analysis_persistence import persist_analysis
from app.services.economic_calendar import (
    get_upcoming_events,
    is_blackout_window,
)
from app.services.instruments import canonical_symbol
from app.services.news_service import (
    aggregate_sentiment,
    fetch_latest_news,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])


# ---------------------------------------------------------------------------
# Currency mapping used for economic-calendar filtering.
# ---------------------------------------------------------------------------

SYMBOL_CURRENCY_MAP = {
    "XAUUSD": ["USD"],
    "DXY": ["USD"],
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "US30": ["USD"],
    "NAS100": ["USD"],
    "BTCUSD": ["USD"],
}


# ---------------------------------------------------------------------------
# Load validated persisted bars.
# ---------------------------------------------------------------------------

def _load_bars(
    db: Session,
    symbol: str,
    timeframe: str,
    limit: int,
) -> list[Bar]:

    rows = (
        db.execute(
            select(MarketBar)
            .where(
                MarketBar.symbol == symbol.upper(),
                MarketBar.timeframe == timeframe.upper(),
            )
            .order_by(MarketBar.bar_time.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    # Database query is newest -> oldest.
    # Analysis engine expects oldest -> newest.
    rows.reverse()

    return [
        Bar(
            r.bar_time,
            r.open,
            r.high,
            r.low,
            r.close,
            r.volume,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Normalize requested timeframes.
# ---------------------------------------------------------------------------

def _normalize_timeframes(
    primary_timeframe: str,
    requested_timeframes: list[str] | None,
) -> list[str]:

    primary = primary_timeframe.upper().strip()

    if requested_timeframes:
        timeframes = [
            tf.upper().strip()
            for tf in requested_timeframes
            if tf and tf.strip()
        ]
    else:
        timeframes = []

    # Always include the primary timeframe.
    if primary not in timeframes:
        timeframes.append(primary)

    # Remove duplicates while preserving order.
    return list(dict.fromkeys(timeframes))


# ---------------------------------------------------------------------------
# Run multi-timeframe analysis.
# ---------------------------------------------------------------------------

@router.post("/run", response_model=SignalOut)
async def run_analysis(
    payload: AnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Signal:

    symbol = canonical_symbol(payload.symbol)

    primary_tf = payload.timeframe.upper().strip()

    requested_tfs = _normalize_timeframes(
        primary_tf,
        payload.timeframes,
    )

    # ---------------------------------------------------------------
    # Load bars for every requested timeframe.
    # ---------------------------------------------------------------

    timeframe_bars: dict[str, list[Bar]] = {}

    for tf in requested_tfs:
        bars = _load_bars(
            db=db,
            symbol=symbol,
            timeframe=tf,
            limit=payload.bar_limit,
        )

        if bars:
            timeframe_bars[tf] = bars

    # Primary timeframe must contain enough validated bars.
    minimum_bars = max(
        10,
        payload.lookback * 2 + 3,
    )

    primary_bars = timeframe_bars.get(primary_tf, [])

    if len(primary_bars) < minimum_bars:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Insufficient validated bars for "
                f"{symbol} {primary_tf}. "
                f"Required at least {minimum_bars}, "
                f"received {len(primary_bars)}."
            ),
        )

    # ---------------------------------------------------------------
    # Correlated symbol for SMT divergence.
    # ---------------------------------------------------------------

    corr_symbol = (
        canonical_symbol(payload.correlated_symbol)
        if payload.correlated_symbol
        else None
    )

    if not corr_symbol and symbol in {
        "XAUUSD",
        "US30",
        "NAS100",
    }:
        corr_symbol = "DXY"

    correlated: dict[str, list[Bar]] = {}

    if corr_symbol:
        for tf in requested_tfs:

            correlated_bars = _load_bars(
                db=db,
                symbol=corr_symbol,
                timeframe=tf,
                limit=payload.bar_limit,
            )

            if correlated_bars:
                correlated[tf] = correlated_bars

    # ---------------------------------------------------------------
    # Economic calendar.
    # ---------------------------------------------------------------

    currencies = SYMBOL_CURRENCY_MAP.get(symbol, [])

    events = []
    blackout = False

    if payload.check_calendar_blackout and currencies:

        all_events = await get_upcoming_events(
            hours_ahead=24
        )

        blackout, _ = await is_blackout_window(
            currencies
        )

        allowed_currencies = {
            currency.upper()
            for currency in currencies
        }

        events = [
            {
                "name": event.name,
                "currency": event.currency,
                "impact": event.impact,
                "event_time": event.event_time.isoformat(),
                "forecast": event.forecast,
                "previous": event.previous,
                "actual": event.actual,
            }
            for event in all_events
            if event.currency.upper()
            in allowed_currencies
        ]

    # ---------------------------------------------------------------
    # News sentiment.
    # ---------------------------------------------------------------

    articles = []

    if payload.use_news_sentiment:
        articles = await fetch_latest_news()

    news_sentiment = (
        aggregate_sentiment(articles)
        if articles
        else None
    )

    # ---------------------------------------------------------------
    # Deterministic SMC multi-timeframe pipeline.
    #
    # This is where the existing:
    # BOS
    # FVG
    # Order Blocks
    # Liquidity Sweeps
    # Displacement
    # SMT
    # Premium/Discount
    # Confluence
    # BUY/SELL classification
    # are calculated.
    # ---------------------------------------------------------------

    result = analyze_multi_timeframe(
        symbol=symbol,
        timeframe_bars=timeframe_bars,
        primary_timeframe=primary_tf,
        correlated_timeframe_bars=correlated,
        news_sentiment=news_sentiment,
        high_impact_events=events,
        calendar_blackout=blackout,
        lookback=payload.lookback,
        min_confidence=payload.min_confidence_to_trade,
        risk_reward_target=payload.risk_reward_target,
    )

    # ---------------------------------------------------------------
    # AI is narrative-only.
    #
    # It CANNOT change:
    # direction
    # confidence
    # entry
    # stop loss
    # take profit
    # confluence
    # ---------------------------------------------------------------

    from types import SimpleNamespace

    plan = SimpleNamespace(
        direction=result.direction,
        confidence=result.confidence,
        entry=(
            result.entry_zone[0]
            if result.entry_zone
            else None
        ),
        stop_loss=result.stop_loss,
        take_profit=(
            result.take_profits[0]
            if result.take_profits
            else None
        ),
        risk_reward=result.risk_reward,
        confluence=result.evidence,
        reasoning=result.reasoning,
    )

    narrative = await generate_narrative(
        plan,
        symbol,
        primary_tf,
    )

    # ---------------------------------------------------------------
    # Persist analysis.
    # ---------------------------------------------------------------

    if payload.persist:

        _, signal = persist_analysis(
            db=db,
            symbol=symbol,
            primary_timeframe=primary_tf,
            result=result,
            narrative=narrative,
            events=events,
            articles=articles,
        )

        return signal

    # ---------------------------------------------------------------
    # Non-persisted analysis.
    # ---------------------------------------------------------------

    signal = Signal(
        id=str(uuid.uuid4()),
        symbol=symbol,
        timeframe=primary_tf,

        direction=(
            SignalDirection.BULLISH
            if result.direction == "bullish"
            else SignalDirection.BEARISH
            if result.direction == "bearish"
            else SignalDirection.NO_TRADE
        ),

        confidence=result.confidence,
        setup_status=result.status,
        market_bias=result.market_bias,

        entry_price=(
            sum(result.entry_zone) / 2
            if result.entry_zone
            else None
        ),

        entry_zone_low=(
            result.entry_zone[0]
            if result.entry_zone
            else None
        ),

        entry_zone_high=(
            result.entry_zone[1]
            if result.entry_zone
            else None
        ),

        invalidation=result.invalidation,

        stop_loss=result.stop_loss,

        take_profit=(
            result.take_profits[0]
            if result.take_profits
            else None
        ),

        take_profits=result.take_profits,

        risk_reward=result.risk_reward,

        confluence=result.evidence,

        reasoning=narrative,

        created_at=datetime.now(timezone.utc),
    )

    return signal


# ---------------------------------------------------------------------------
# APK compatibility endpoint.
#
# The current Flutter APK calls:
# GET /api/v1/analysis/{symbol}
#
# This reuses the existing run_analysis() pipeline.
# ---------------------------------------------------------------------------

@router.get(
    "/{symbol}",
    response_model=SignalOut,
)
async def get_analysis(
    symbol: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Signal:

    normalized_symbol = canonical_symbol(symbol)

    payload = AnalysisRequest(
        symbol=normalized_symbol,
        timeframe="M15",
        persist=True,
    )

    return await run_analysis(
        payload=payload,
        db=db,
        current_user=current_user,
    )


# ---------------------------------------------------------------------------
# Signal history.
# ---------------------------------------------------------------------------

@router.get(
    "/signals",
    response_model=list[SignalOut],
)
def list_signals(
    symbol: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Signal]:

    limit = max(
        1,
        min(limit, 200),
    )

    query = select(Signal)

    if symbol:
        query = query.where(
            Signal.symbol
            == canonical_symbol(symbol)
        )

    return (
        db.execute(
            query
            .order_by(Signal.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# Individual analysis run.
# ---------------------------------------------------------------------------

@router.get(
    "/runs/{run_id}",
    response_model=AnalysisRunOut,
)
def get_analysis_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalysisRun:

    run = db.get(
        AnalysisRun,
        run_id,
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis run not found",
        )

    return run
