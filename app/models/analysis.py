"""Persistence models for auditable analysis runs and detector evidence."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    primary_timeframe: Mapped[str] = mapped_column(String, nullable=False)
    timeframes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    market_bias: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confluence_score: Mapped[float] = mapped_column(Float, nullable=False)
    entry_zone_low: Mapped[float | None] = mapped_column(Float)
    entry_zone_high: Mapped[float | None] = mapped_column(Float)
    invalidation: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float)
    take_profits: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_reward: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_analysis_runs_symbol_created", "symbol", "created_at"),)


class StructureEventRecord(Base):
    __tablename__ = "structure_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    analysis_run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    broken_swing_price: Mapped[float] = mapped_column(Float, nullable=False)


class FairValueGapRecord(Base):
    __tablename__ = "fair_value_gaps"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    analysis_run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    top: Mapped[float] = mapped_column(Float, nullable=False)
    bottom: Mapped[float] = mapped_column(Float, nullable=False)
    filled: Mapped[bool] = mapped_column(default=False, nullable=False)
    fill_index: Mapped[int | None] = mapped_column(Integer)


class OrderBlockRecord(Base):
    __tablename__ = "order_blocks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    analysis_run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    top: Mapped[float] = mapped_column(Float, nullable=False)
    bottom: Mapped[float] = mapped_column(Float, nullable=False)
    mitigated: Mapped[bool] = mapped_column(default=False, nullable=False)
    mitigation_index: Mapped[int | None] = mapped_column(Integer)
    break_index: Mapped[int | None] = mapped_column(Integer)


class LiquiditySweepRecord(Base):
    __tablename__ = "liquidity_sweeps"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    analysis_run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    swept_level: Mapped[float] = mapped_column(Float, nullable=False)
    swept_swing_index: Mapped[int] = mapped_column(Integer, nullable=False)


class EconomicEventRecord(Base):
    __tablename__ = "economic_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    analysis_run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    impact: Mapped[str] = mapped_column(String, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast: Mapped[str | None] = mapped_column(String)
    previous: Mapped[str | None] = mapped_column(String)
    actual: Mapped[str | None] = mapped_column(String)


class NewsArticleRecord(Base):
    __tablename__ = "news_articles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    analysis_run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    published: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sentiment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
