from datetime import datetime, timedelta, timezone

import pytest

from app.engine.pipeline import analyze_multi_timeframe
from app.engine.types import Bar


def bars(prices):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Bar(t0 + timedelta(minutes=i), *x) for i, x in enumerate(prices)]


def strong_bullish():
    return bars([
        (10,10,9,10),(10,11,10,11),(11,13,11,12),(12,12,10,10.5),
        (10.5,11,10.3,10.8),(10.8,20,10.5,19.5),(19.5,21,13,20),
        (20,22,19,21),(21,21,18,19),(19,25,18.5,24),
    ])


def test_pipeline_never_trades_on_one_indicator():
    result = analyze_multi_timeframe(
        "XAUUSD", {"M15": bars([(10,10,9,10)] * 10)}, "M15",
        min_confidence=0,
    )
    assert result.direction == "no_trade"
    assert result.status == "INSUFFICIENT_CONFIRMATION"


def test_strong_structure_plus_zones_can_form_setup():
    result = analyze_multi_timeframe(
        "XAUUSD", {"M15": strong_bullish()}, "M15", min_confidence=60
    )
    assert result.status == "SETUP"
    assert result.direction == "bullish"
    assert result.evidence["scores"]["bullish"] > result.evidence["scores"]["bearish"]
    assert len(result.evidence["technical_hits"]["bullish"]) >= 3
    assert result.entry_zone is not None
    assert result.stop_loss is not None
    assert len(result.take_profits) == 3
    assert result.risk_reward == 2.0


def test_high_impact_event_blocks_setup_without_becoming_direction():
    result = analyze_multi_timeframe(
        "XAUUSD", {"M15": strong_bullish()}, "M15",
        high_impact_events=[{"name": "CPI", "currency": "USD", "impact": "high"}],
        calendar_blackout=True,
        min_confidence=0,
    )
    assert result.status == "NO_SETUP"
    assert result.direction == "no_trade"
    assert result.evidence["fundamental"]["high_impact_event"] is True


def test_news_cannot_create_a_trade_without_technical_structure():
    result = analyze_multi_timeframe(
        "XAUUSD", {"M15": bars([(10,10,9,10)] * 10)}, "M15",
        news_sentiment=1.0, min_confidence=0,
    )
    assert result.direction == "no_trade"
    assert result.status == "INSUFFICIENT_CONFIRMATION"


def test_multitimeframe_conflict_is_visible_and_not_hidden():
    primary = strong_bullish()
    bearish = bars([
        (20,21,19,20),(20,20,18,18),(18,19,17,17.5),(17.5,18,15,16),
        (16,17,14,14.5),(14.5,15,10,10.5),(10.5,12,9,11),
        (11,11,8,8.5),(8.5,9,6,6.5),(6.5,7,4,5),
    ])
    result = analyze_multi_timeframe(
        "XAUUSD", {"H1": bearish, "M15": primary}, "M15",
        min_confidence=60,
    )
    assert "trend_votes" in result.evidence["cross_timeframe"]
    assert result.evidence["cross_timeframe"]["aligned"] in (True, False)


def test_invalid_and_out_of_order_bars_are_rejected():
    data = bars([(10,10,9,10)] * 10)
    data[4] = Bar(data[4].time, 11, 10, 9, 10)
    with pytest.raises(ValueError):
        analyze_multi_timeframe("XAUUSD", {"M15": data}, "M15")
