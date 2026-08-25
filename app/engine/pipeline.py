"""
Production analysis pipeline.

Validated bars -> per-timeframe detectors -> cross-timeframe context ->
transparent confluence -> risk plan -> explainable final classification.

This module has no SQLAlchemy/FastAPI dependencies, so it can be unit-tested
purely with deterministic OHLC fixtures.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from app.engine.displacement import is_displacement_candle
from app.engine.fvg import detect_fair_value_gaps
from app.engine.liquidity import detect_liquidity_sweeps, find_equal_levels
from app.engine.order_blocks import detect_order_blocks
from app.engine.premium_discount import compute_dealing_range
from app.engine.sessions import compute_session_windows
from app.engine.smt import detect_smt_divergence
from app.engine.structure import detect_structure_events, find_swing_points, label_swings
from app.engine.types import AnalysisResult, Bar, FairValueGap, OrderBlock, TimeframeEvidence


# Technical evidence is deliberately dominant. Fundamental/news context can
# confirm or reduce confidence but cannot create a setup by itself.
WEIGHTS = {
    "structure": 28,
    "order_block": 14,
    "fvg": 10,
    "liquidity": 10,
    "premium_discount": 10,
    "displacement": 10,
    "smt": 5,
    "session": 3,
    "fundamental": 5,
    "news": 5,
}
TECHNICAL_KEYS = {
    "structure", "order_block", "fvg", "liquidity",
    "premium_discount", "displacement", "smt", "session",
}


def _validate_bars(bars: Iterable[Bar]) -> list[Bar]:
    out = list(bars)
    if any(b.high < max(b.open, b.close) or b.low > min(b.open, b.close) or b.high < b.low for b in out):
        raise ValueError("Invalid OHLC data: high/low do not contain open/close.")
    for a, b in zip(out, out[1:]):
        if b.time <= a.time:
            raise ValueError("Bars must be strictly chronological.")
    return out


def _latest_direction(events):
    return events[-1].direction if events else None


def _serialize_gap(g: FairValueGap) -> dict:
    return {
        "index": g.index, "time": g.time.isoformat(), "direction": g.direction,
        "top": g.top, "bottom": g.bottom, "filled": g.filled, "fill_index": g.fill_index,
    }


def _serialize_ob(o: OrderBlock) -> dict:
    return {
        "index": o.index, "time": o.time.isoformat(), "direction": o.direction,
        "top": o.top, "bottom": o.bottom, "mitigated": o.mitigated,
        "mitigation_index": o.mitigation_index, "break_index": o.break_index,
    }


def _tf_evidence(
    timeframe: str,
    bars: list[Bar],
    correlated: list[Bar] | None,
    lookback: int,
) -> TimeframeEvidence:
    swings = find_swing_points(bars, lookback)
    events, trend = detect_structure_events(bars, lookback)
    fvgs = detect_fair_value_gaps(bars, require_displacement=True)
    obs = detect_order_blocks(bars, lookback)
    sweeps = detect_liquidity_sweeps(bars, lookback)
    dr = compute_dealing_range(bars, lookback)
    windows = compute_session_windows(bars)
    displacement_indices = tuple(
        i for i in range(len(bars))
        if is_displacement_candle(bars, i)
    )
    smt = detect_smt_divergence(bars, correlated, lookback) if correlated else []

    session_json = {
        name: {"high": w.high, "low": w.low, "swept": w.swept}
        for name, w in windows.items()
    }
    return TimeframeEvidence(
        timeframe=timeframe,
        trend=trend,
        structure_events=tuple(events),
        swings=tuple(swings),
        fvgs=tuple(fvgs),
        order_blocks=tuple(obs),
        sweeps=tuple(sweeps),
        dealing_range=dr,
        displacement_indices=displacement_indices,
        session=session_json,
        smt=tuple(smt),
    )




def _cluster_swing_levels(prices: list[float], tolerance_pct: float = 0.05) -> list[float]:
    levels: list[float] = []
    for p in sorted(prices):
        if not levels or abs(p - levels[-1]) / max(abs(levels[-1]), 1e-12) * 100 > tolerance_pct:
            levels.append(p)
    return levels


def _evidence_json(e: TimeframeEvidence, current_price: float) -> dict:
    labels = label_swings(list(e.swings))
    dr = e.dealing_range
    return {
        "timeframe": e.timeframe,
        "trend": e.trend,
        "swings": [
            {"index": s.index, "time": s.time.isoformat(), "price": s.price,
             "kind": s.kind.value, "confirmed_at": s.confirmed_at,
             "label": labels.get(s.index)}
            for s in e.swings
        ],
        "structure": [
            {"index": x.index, "time": x.time.isoformat(), "type": x.event_type.value,
             "direction": x.direction, "price": x.price,
             "broken_swing": x.broken_swing.price}
            for x in e.structure_events
        ],
        "fvgs": [_serialize_gap(x) for x in e.fvgs],
        "order_blocks": [_serialize_ob(x) for x in e.order_blocks],
        "liquidity_sweeps": [
            {"index": x.index, "time": x.time.isoformat(), "direction": x.direction,
             "level": x.swept_level, "swing_index": x.swept_swing_index}
            for x in e.sweeps
        ],
        "equal_levels": {
            "highs": _cluster_swing_levels([s.price for s in e.swings if s.kind.value == "high"]),
            "lows": _cluster_swing_levels([s.price for s in e.swings if s.kind.value == "low"]),
        },
        "dealing_range": (
            {"high": dr.range_high, "low": dr.range_low, "equilibrium": dr.equilibrium,
             "zone": dr.zone_for(current_price)}
            if dr else None
        ),
        "displacement_indices": list(e.displacement_indices),
        "sessions": e.session,
        "smt": [{"index": x.index, "time": x.time.isoformat(), "direction": x.direction, "detail": x.detail}
                for x in e.smt],
    }


def analyze_multi_timeframe(
    symbol: str,
    timeframe_bars: dict[str, list[Bar]],
    primary_timeframe: str,
    correlated_timeframe_bars: dict[str, list[Bar]] | None = None,
    news_sentiment: float | None = None,
    high_impact_events: list[dict] | None = None,
    calendar_blackout: bool = False,
    lookback: int = 2,
    min_confidence: float = 65.0,
    risk_reward_target: float = 2.0,
) -> AnalysisResult:
    if primary_timeframe not in timeframe_bars:
        return AnalysisResult(
            "INSUFFICIENT_CONFIRMATION", "no_trade", 0.0, 0.0, symbol,
            primary_timeframe, list(timeframe_bars), "unknown", None, None,
            None, [], None, {}, "Primary timeframe data is unavailable."
        )

    evidences: dict[str, TimeframeEvidence] = {}
    for tf, raw in timeframe_bars.items():
        bars = _validate_bars(raw)
        if len(bars) < (2 * lookback + 3):
            continue
        corr = (correlated_timeframe_bars or {}).get(tf)
        evidences[tf] = _tf_evidence(tf, bars, corr, lookback)

    if primary_timeframe not in evidences:
        return AnalysisResult(
            "INSUFFICIENT_CONFIRMATION", "no_trade", 0.0, 0.0, symbol,
            primary_timeframe, list(timeframe_bars), "unknown", None, None,
            None, [], None, {}, "Insufficient confirmed bars on the primary timeframe."
        )

    primary = evidences[primary_timeframe]
    directions = {"bullish": 0, "bearish": 0}
    for e in evidences.values():
        if e.trend in directions:
            directions[e.trend] += 1
    htf_bias = max(directions, key=directions.get) if max(directions.values()) else "neutral"

    last_price = timeframe_bars[primary_timeframe][-1].close
    factors = {
        "bullish": {k: False for k in WEIGHTS},
        "bearish": {k: False for k in WEIGHTS},
    }

    for direction in ("bullish", "bearish"):
        factors[direction]["structure"] = any(
            e.structure_events and e.structure_events[-1].direction == direction
            for e in evidences.values()
        )
        factors[direction]["order_block"] = any(
            o.direction == direction and not o.mitigated
            for e in evidences.values() for o in e.order_blocks
        )
        factors[direction]["fvg"] = any(
            g.direction == direction and not g.filled
            for e in evidences.values() for g in e.fvgs
        )
        # A sell-side sweep supports a bullish reversal; buy-side supports bearish.
        sweep_dir = "sell_side" if direction == "bullish" else "buy_side"
        factors[direction]["liquidity"] = any(
            s.direction == sweep_dir for e in evidences.values() for s in e.sweeps
        )
        dr = primary.dealing_range
        factors[direction]["premium_discount"] = bool(
            dr and dr.zone_for(last_price) == ("discount" if direction == "bullish" else "premium")
        )
        factors[direction]["displacement"] = bool(primary.displacement_indices)
        factors[direction]["smt"] = any(x.direction == direction for x in primary.smt)
        # Session is context, never a setup trigger by itself.
        hour = timeframe_bars[primary_timeframe][-1].time.hour
        factors[direction]["session"] = 7 <= hour < 21
        factors[direction]["fundamental"] = False
        factors[direction]["news"] = (
            news_sentiment is not None and
            ((direction == "bullish" and news_sentiment > 0.15) or
             (direction == "bearish" and news_sentiment < -0.15))
        )

    # Fundamental context: high-impact events reduce confidence; an event
    # is never treated as a technical direction signal.
    event_risk = calendar_blackout
    if news_sentiment is not None and abs(news_sentiment) >= 0.15:
        n_direction = "bullish" if news_sentiment > 0 else "bearish"
        factors[n_direction]["fundamental"] = bool(not event_risk)

    raw_scores = {
        d: sum(WEIGHTS[k] for k, hit in factors[d].items() if hit)
        for d in ("bullish", "bearish")
    }
    best = "bullish" if raw_scores["bullish"] > raw_scores["bearish"] else "bearish"
    score = raw_scores[best]

    # Technical evidence requirements prevent one-indicator signals.
    technical_hits = [k for k in TECHNICAL_KEYS if factors[best][k]]
    structure_ok = factors[best]["structure"]
    cross_tf_ok = len(evidences) == 1 or directions[best] >= max(1, (len(evidences) + 1) // 2)
    opposing = raw_scores["bearish" if best == "bullish" else "bullish"]
    materially_conflicted = opposing >= max(20, score - 10)
    confidence = round(min(100.0, score * (0.75 if materially_conflicted else 1.0)), 1)

    status = "SETUP" if (
        structure_ok and len(technical_hits) >= 3 and cross_tf_ok and
        not materially_conflicted and confidence >= min_confidence and not event_risk
    ) else "NO_SETUP"
    if not technical_hits:
        status = "INSUFFICIENT_CONFIRMATION"
    if event_risk and status == "SETUP":
        status = "NO_SETUP"

    chosen = primary
    direction = best if status == "SETUP" else "no_trade"

    active_obs = [o for o in chosen.order_blocks if o.direction == best and not o.mitigated]
    active_fvgs = [g for g in chosen.fvgs if g.direction == best and not g.filled]
    entry_zone = None
    invalidation = None
    if active_obs:
        o = active_obs[-1]
        entry_zone = (o.bottom, o.top)
        invalidation = o.bottom if best == "bullish" else o.top
    elif active_fvgs:
        g = active_fvgs[-1]
        entry_zone = (g.bottom, g.top)
        invalidation = g.bottom if best == "bullish" else g.top

    entry = sum(entry_zone) / 2 if entry_zone else last_price
    stop = None
    tps: list[float] = []
    rr = None
    if status == "SETUP" and invalidation is not None:
        # Add a small deterministic buffer equal to 10% of the zone width.
        width = max(abs(entry_zone[1] - entry_zone[0]), last_price * 0.0001)
        stop = invalidation - width * 0.10 if best == "bullish" else invalidation + width * 0.10
        risk = abs(entry - stop)
        if risk > 0:
            tps = [
                entry + risk * risk_reward_target if best == "bullish" else entry - risk * risk_reward_target,
                entry + risk * (risk_reward_target + 1.0) if best == "bullish" else entry - risk * (risk_reward_target + 1.0),
                entry + risk * (risk_reward_target + 2.0) if best == "bullish" else entry - risk * (risk_reward_target + 2.0),
            ]
            rr = round(abs(tps[0] - entry) / risk, 2)

    evidence = {
        "schema_version": "2.1",
        "factor_weights": WEIGHTS,
        "scores": raw_scores,
        "technical_hits": {d: [k for k in TECHNICAL_KEYS if factors[d][k]] for d in factors},
        "factors": factors,
        "cross_timeframe": {
            "trend_votes": directions,
            "bias": htf_bias,
            "aligned": cross_tf_ok, "materially_conflicted": materially_conflicted,
        },
        "market_context": {"correlated_trends": {tf: e.trend for tf, e in ((correlated_timeframe_bars and {tf: _tf_evidence(tf, bars, None, lookback) for tf, bars in correlated_timeframe_bars.items()}) or {}).items()}},
        "fundamental": {
            "high_impact_event": event_risk,
            "events": high_impact_events or [],
            "news_sentiment": news_sentiment,
        },
        "timeframes": {
            tf: _evidence_json(e, timeframe_bars[tf][-1].close) for tf, e in evidences.items()
        },
    }

    reasons = []
    if structure_ok:
        reasons.append(f"{best.upper()} structure confirmed by {primary.structure_events[-1].event_type.value}")
    if active_obs:
        reasons.append("unmitigated order block present")
    if active_fvgs:
        reasons.append("unfilled fair value gap present")
    if factors[best]["liquidity"]:
        reasons.append("opposing-side liquidity sweep detected")
    if factors[best]["premium_discount"]:
        reasons.append("price is in the preferred premium/discount zone")
    if factors[best]["smt"]:
        reasons.append("SMT divergence supports the direction")
    if event_risk:
        reasons.append("high-impact economic event risk blocks the setup")
    if not reasons:
        reasons.append("insufficient independent technical evidence")
    reasoning = "; ".join(reasons) + "."

    return AnalysisResult(
        status=status,
        direction=direction,
        confidence=confidence,
        confluence_score=score,
        symbol=symbol,
        primary_timeframe=primary_timeframe,
        timeframes=list(evidences),
        market_bias=htf_bias,
        entry_zone=entry_zone,
        invalidation=invalidation,
        stop_loss=stop,
        take_profits=tps,
        risk_reward=rr,
        evidence=evidence,
        reasoning=reasoning,
    )
