"""
Backward-compatible confluence facade.

The production scoring logic now lives in `pipeline.py`. This facade keeps
the original `analyze(...) -> TradePlan` contract used by existing callers
while delegating to the same deterministic multi-factor engine.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from app.engine.pipeline import analyze_multi_timeframe
from app.engine.types import Bar


@dataclass
class TradePlan:
    direction: str
    confidence: float
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    confluence: dict = field(default_factory=dict)
    reasoning: str = ""


def analyze(
    bars: list[Bar],
    correlated_bars: list[Bar] | None = None,
    news_sentiment: float | None = None,
    calendar_blackout: bool = False,
    lookback: int = 2,
    min_confidence_to_trade: float = 60.0,
    risk_reward_target: float = 2.0,
) -> TradePlan:
    events = [{"impact": "high", "name": "blackout"}] if calendar_blackout else []
    result = analyze_multi_timeframe(
        symbol="UNKNOWN",
        timeframe_bars={"M15": bars},
        primary_timeframe="M15",
        correlated_timeframe_bars={"M15": correlated_bars} if correlated_bars else None,
        news_sentiment=news_sentiment,
        high_impact_events=events,
        calendar_blackout=calendar_blackout,
        lookback=lookback,
        min_confidence=min_confidence_to_trade,
        risk_reward_target=risk_reward_target,
    )
    if calendar_blackout:
        result.evidence["blackout"] = True
    return TradePlan(
        direction=result.direction,
        confidence=result.confidence,
        entry=(sum(result.entry_zone) / 2 if result.entry_zone else None),
        stop_loss=result.stop_loss,
        take_profit=result.take_profits[0] if result.take_profits else None,
        risk_reward=result.risk_reward,
        confluence=result.evidence,
        reasoning=result.reasoning,
    )
