"""
Pydantic schemas for analysis requests/responses and signal history.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.signal import SignalDirection, SignalStatus


class AnalysisRequest(BaseModel):
    symbol: str

    # Primary timeframe used for the main analysis result.
    timeframe: str = "M15"

    # Additional timeframes used for multi-timeframe analysis.
    # Example: ["M5", "M15", "H1", "H4"]
    timeframes: list[str] | None = None

    # Optional correlated symbol for SMT divergence.
    correlated_symbol: str | None = None

    # Market-data settings.
    bar_limit: int = 200
    lookback: int = 2

    # Signal settings.
    min_confidence_to_trade: float = 60.0
    risk_reward_target: float = 2.0

    # External context.
    use_news_sentiment: bool = True
    check_calendar_blackout: bool = True

    # Whether to persist the analysis/signal.
    persist: bool = True


class ConfluenceFactorOut(BaseModel):
    hit: bool
    detail: str | None = None
    count: int | None = None
    level: float | None = None
    zone: str | None = None
    value: float | None = None


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    timeframe: str

    # Final trading decision.
    direction: SignalDirection
    confidence: float

    # Setup information.
    setup_status: str
    market_bias: str

    # Entry.
    entry_price: float | None
    entry_zone_low: float | None
    entry_zone_high: float | None

    # Risk management.
    invalidation: float | None
    stop_loss: float | None
    take_profit: float | None
    take_profits: list[float]
    risk_reward: float | None

    # SMC/confluence evidence.
    confluence: dict

    # Human-readable explanation.
    reasoning: str | None

    # Signal lifecycle status.
    status: SignalStatus

    created_at: datetime


class PendingSignalOut(BaseModel):
    """
    What the MT5 EA polls for -- a trimmed view with just what it needs
    to place an order.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    direction: SignalDirection
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None


class ExecutionReport(BaseModel):
    signal_id: str
    mt5_ticket: int | None = None
    executed_price: float | None = None
    volume: float | None = None

    # "filled" | "rejected" | "closed"
    status: str

    detail: str | None = None


class AnalysisRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str

    primary_timeframe: str
    timeframes: list[str]

    status: str
    direction: str
    market_bias: str
    confidence: float
    confluence_score: float

    entry_zone_low: float | None
    entry_zone_high: float | None
    invalidation: float | None
    stop_loss: float | None
    take_profits: list[float]
    risk_reward: float | None

    # Detailed detector evidence.
    evidence: dict

    # Full explanation.
    reasoning: str

    created_at: datetime