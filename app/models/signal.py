"""
AI-generated trade signals and their MT5 execution lifecycle.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SignalDirection(str, enum.Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NO_TRADE = "no_trade"


class SignalStatus(str, enum.Enum):
    PENDING = "pending"        # generated, waiting for the EA to pick it up
    ACKNOWLEDGED = "acknowledged"  # EA has fetched it
    EXECUTED = "executed"      # EA reported a fill
    EXPIRED = "expired"        # not acted on in time
    REJECTED = "rejected"      # EA/broker rejected it


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    analysis_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("analysis_runs.id"), nullable=True)

    symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)

    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0-100
    setup_status: Mapped[str] = mapped_column(String, nullable=False, default="NO_SETUP")
    market_bias: Mapped[str] = mapped_column(String, nullable=False, default="neutral")
    entry_zone_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_zone_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    invalidation: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profits: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Full machine-readable breakdown of every confluence factor that fed
    # the score (structure, FVG, OB, liquidity, session, news blackout,
    # SMT divergence) -- stored so the UI/journal can show *why*.
    confluence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus), default=SignalStatus.PENDING, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TradeExecution(Base):
    """Reported back by the MT5 EA once it acts on a signal."""

    __tablename__ = "trade_executions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    signal_id: Mapped[str] = mapped_column(String, ForeignKey("signals.id"), nullable=False)

    mt5_ticket: Mapped[int | None] = mapped_column(nullable=True)
    executed_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)  # filled/rejected/closed
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
