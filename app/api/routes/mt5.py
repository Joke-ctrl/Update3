"""
MT5 Expert Advisor bridge.

Two directions of traffic:
  - EA -> backend: /mt5/ingest persists real OHLC bars the EA sends, which
    is what the analysis engine reads. No data is fabricated here; if the
    EA hasn't sent bars for a symbol/timeframe, analysis on it will
    correctly report "insufficient bars" rather than inventing a result.
  - backend -> EA: /mt5/pending-signals is polled by the EA to find
    signals the AI engine generated that are ready to execute; the EA
    reports back what happened via /mt5/execution-report.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.config import get_settings
from app.models.market_data import MarketBar
from app.models.signal import Signal, SignalStatus, SignalDirection, TradeExecution
from app.schemas.signal import ExecutionReport, PendingSignalOut
from app.services.instruments import canonical_symbol

router = APIRouter(prefix="/mt5", tags=["mt5"])


class OHLCBar(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class OpenPosition(BaseModel):
    ticket: int
    symbol: str
    volume: float
    open_price: float
    profit: float


class MT5Payload(BaseModel):
    symbol: str
    timeframe: str = "M1"
    spread: float = 0.0
    bars: list[OHLCBar] = Field(min_length=1, max_length=5000)
    open_positions: list[OpenPosition] = []
    tick_time: str | None = None


class MT5Response(BaseModel):
    status: str
    bars_stored: int
    bars_skipped_duplicate: int
    message: str


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@router.post("/ingest", response_model=MT5Response)
def ingest(
    payload: MT5Payload,
    db: Session = Depends(get_db),
    x_mt5_api_key: str | None = Header(default=None, alias="X-MT5-API-Key"),
) -> MT5Response:
    configured_key = get_settings().MT5_API_KEY
    if configured_key and x_mt5_api_key != configured_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MT5 API key")

    canonical = canonical_symbol(payload.symbol)
    stored = 0
    skipped = 0

    for bar in payload.bars:
        if not (bar.high >= max(bar.open, bar.close) and bar.low <= min(bar.open, bar.close) and bar.high >= bar.low):
            raise HTTPException(status_code=422, detail=f"Invalid OHLC bar at {bar.time}")
        bar_time = _parse_time(bar.time)
        exists = db.execute(
            select(MarketBar).where(
                MarketBar.symbol == canonical,
                MarketBar.timeframe == payload.timeframe,
                MarketBar.bar_time == bar_time,
            )
        ).scalar_one_or_none()

        if exists:
            skipped += 1
            continue

        db.add(
            MarketBar(
                symbol=canonical,
                timeframe=payload.timeframe,
                bar_time=bar_time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                spread=payload.spread,
            )
        )
        stored += 1

    db.commit()

    return MT5Response(
        status="ok",
        bars_stored=stored,
        bars_skipped_duplicate=skipped,
        message=f"{stored} new bars stored for {canonical} {payload.timeframe} ({skipped} duplicates skipped).",
    )


@router.get("/pending-signals", response_model=list[PendingSignalOut])
def pending_signals(
    symbol: str | None = None,
    db: Session = Depends(get_db),
    x_mt5_api_key: str | None = Header(default=None, alias="X-MT5-API-Key"),
) -> list[Signal]:
    configured_key = get_settings().MT5_API_KEY
    if configured_key and x_mt5_api_key != configured_key:
        raise HTTPException(status_code=401, detail="Invalid MT5 API key")
    query = select(Signal).where(
        Signal.status == SignalStatus.PENDING,
        Signal.setup_status == "SETUP",
        or_(Signal.direction == SignalDirection.BULLISH, Signal.direction == SignalDirection.BEARISH),
    )
    if symbol:
        query = query.where(Signal.symbol == canonical_symbol(symbol))
    signals = db.execute(query.order_by(Signal.created_at.desc()).limit(20)).scalars().all()

    # Mark as acknowledged so the same signal isn't re-fetched/re-executed
    # by a second EA poll before it reports back.
    for s in signals:
        s.status = SignalStatus.ACKNOWLEDGED
    db.commit()

    return signals


@router.post("/execution-report")
def execution_report(
    report: ExecutionReport,
    db: Session = Depends(get_db),
    x_mt5_api_key: str | None = Header(default=None, alias="X-MT5-API-Key"),
) -> dict:
    configured_key = get_settings().MT5_API_KEY
    if configured_key and x_mt5_api_key != configured_key:
        raise HTTPException(status_code=401, detail="Invalid MT5 API key")
    signal = db.get(Signal, report.signal_id)
    if signal is None:
        return {"status": "error", "message": "Unknown signal_id"}

    execution = TradeExecution(
        signal_id=report.signal_id,
        mt5_ticket=report.mt5_ticket,
        executed_price=report.executed_price,
        volume=report.volume,
        status=report.status,
        detail=report.detail,
    )
    db.add(execution)

    signal.status = SignalStatus.EXECUTED if report.status == "filled" else SignalStatus.REJECTED
    db.commit()

    return {"status": "ok", "message": f"Execution recorded for signal {report.signal_id}"}
