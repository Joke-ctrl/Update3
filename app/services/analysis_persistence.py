"""Persistence service for analysis runs and detector evidence.

Keeps SQLAlchemy concerns out of the deterministic SMC engine and makes the
write path independently testable.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.analysis import (
    AnalysisRun, EconomicEventRecord, FairValueGapRecord,
    LiquiditySweepRecord, NewsArticleRecord, OrderBlockRecord, StructureEventRecord,
)
from app.models.signal import Signal, SignalDirection


def persist_analysis(
    db: Session,
    symbol: str,
    primary_timeframe: str,
    result,
    narrative: str,
    events: list[dict],
    articles: list,
) -> tuple[AnalysisRun, Signal]:
    run = AnalysisRun(
        symbol=symbol,
        primary_timeframe=primary_timeframe,
        timeframes=result.timeframes,
        status=result.status,
        direction=result.direction,
        market_bias=result.market_bias,
        confidence=result.confidence,
        confluence_score=result.confluence_score,
        entry_zone_low=result.entry_zone[0] if result.entry_zone else None,
        entry_zone_high=result.entry_zone[1] if result.entry_zone else None,
        invalidation=result.invalidation,
        stop_loss=result.stop_loss,
        take_profits=result.take_profits,
        risk_reward=result.risk_reward,
        evidence=result.evidence,
        reasoning=narrative,
    )
    db.add(run)
    db.flush()

    for tf, data in result.evidence.get("timeframes", {}).items():
        for x in data.get("structure", []):
            db.add(StructureEventRecord(
                analysis_run_id=run.id, symbol=symbol, timeframe=tf,
                event_index=x["index"], event_time=datetime.fromisoformat(x["time"]),
                event_type=x["type"], direction=x["direction"], price=x["price"],
                broken_swing_price=x["broken_swing"],
            ))
        for x in data.get("fvgs", []):
            db.add(FairValueGapRecord(
                analysis_run_id=run.id, symbol=symbol, timeframe=tf,
                event_index=x["index"], event_time=datetime.fromisoformat(x["time"]),
                direction=x["direction"], top=x["top"], bottom=x["bottom"],
                filled=x["filled"], fill_index=x.get("fill_index"),
            ))
        for x in data.get("order_blocks", []):
            db.add(OrderBlockRecord(
                analysis_run_id=run.id, symbol=symbol, timeframe=tf,
                event_index=x["index"], event_time=datetime.fromisoformat(x["time"]),
                direction=x["direction"], top=x["top"], bottom=x["bottom"],
                mitigated=x["mitigated"], mitigation_index=x.get("mitigation_index"),
                break_index=x.get("break_index"),
            ))
        for x in data.get("liquidity_sweeps", []):
            db.add(LiquiditySweepRecord(
                analysis_run_id=run.id, symbol=symbol, timeframe=tf,
                event_index=x["index"], event_time=datetime.fromisoformat(x["time"]),
                direction=x["direction"], swept_level=x["level"],
                swept_swing_index=x["swing_index"],
            ))

    for e in events:
        db.add(EconomicEventRecord(
            analysis_run_id=run.id, name=e["name"], currency=e["currency"],
            impact=e["impact"], event_time=datetime.fromisoformat(e["event_time"]),
            forecast=e.get("forecast"), previous=e.get("previous"), actual=e.get("actual"),
        ))
    for a in articles:
        db.add(NewsArticleRecord(
            analysis_run_id=run.id, title=a.title, link=a.link,
            published=a.published, summary=a.summary, sentiment=a.sentiment,
        ))

    signal = Signal(
        analysis_run_id=run.id,
        symbol=symbol,
        timeframe=primary_timeframe,
        direction=(
            SignalDirection.BULLISH if result.direction == "bullish"
            else SignalDirection.BEARISH if result.direction == "bearish"
            else SignalDirection.NO_TRADE
        ),
        confidence=result.confidence,
        setup_status=result.status,
        market_bias=result.market_bias,
        entry_price=sum(result.entry_zone) / 2 if result.entry_zone else None,
        entry_zone_low=result.entry_zone[0] if result.entry_zone else None,
        entry_zone_high=result.entry_zone[1] if result.entry_zone else None,
        invalidation=result.invalidation,
        stop_loss=result.stop_loss,
        take_profit=result.take_profits[0] if result.take_profits else None,
        take_profits=result.take_profits,
        risk_reward=result.risk_reward,
        confluence=result.evidence,
        reasoning=narrative,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return run, signal
