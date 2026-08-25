"""
Shared deterministic domain types for the MarketKill3r SMC engine.
All detectors consume/produce these immutable-ish dataclasses so the
pipeline can compose evidence without coupling detectors to SQLAlchemy.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class SwingType(str, enum.Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class SwingPoint:
    index: int
    time: datetime
    price: float
    kind: SwingType
    # A fractal at index i is only known once i+lookback is closed.
    confirmed_at: int | None = None


class StructureLabel(str, enum.Enum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"


class StructureEventType(str, enum.Enum):
    BOS = "BOS"
    CHOCH = "CHoCH"


@dataclass(frozen=True)
class StructureEvent:
    event_type: StructureEventType
    index: int
    time: datetime
    price: float
    direction: str
    broken_swing: SwingPoint


@dataclass
class FairValueGap:
    index: int
    time: datetime
    direction: str
    top: float
    bottom: float
    filled: bool = False
    fill_index: int | None = None


@dataclass
class OrderBlock:
    index: int
    time: datetime
    direction: str
    top: float
    bottom: float
    mitigated: bool = False
    mitigation_index: int | None = None
    break_index: int | None = None


@dataclass(frozen=True)
class LiquiditySweep:
    index: int
    time: datetime
    direction: str
    swept_level: float
    swept_swing_index: int


@dataclass
class SessionWindow:
    name: str
    high: float | None = None
    low: float | None = None
    swept: bool = False


@dataclass(frozen=True)
class SMTDivergence:
    index: int
    time: datetime
    direction: str
    detail: str


@dataclass(frozen=True)
class TimeframeEvidence:
    timeframe: str
    trend: str | None
    structure_events: tuple[StructureEvent, ...]
    swings: tuple[SwingPoint, ...]
    fvgs: tuple[FairValueGap, ...]
    order_blocks: tuple[OrderBlock, ...]
    sweeps: tuple[LiquiditySweep, ...]
    dealing_range: object | None
    displacement_indices: tuple[int, ...]
    session: dict
    smt: tuple[SMTDivergence, ...]


@dataclass
class AnalysisResult:
    status: str
    direction: str
    confidence: float
    confluence_score: float
    symbol: str
    primary_timeframe: str
    timeframes: list[str]
    market_bias: str
    entry_zone: tuple[float, float] | None
    invalidation: float | None
    stop_loss: float | None
    take_profits: list[float]
    risk_reward: float | None
    evidence: dict
    reasoning: str
