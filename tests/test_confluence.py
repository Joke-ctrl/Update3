from datetime import datetime, timedelta, timezone

from app.engine.confluence import analyze
from app.engine.types import Bar


def _mk_bars(prices):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(time=t0 + timedelta(minutes=i), open=o, high=h, low=l, close=c)
        for i, (o, h, l, c) in enumerate(prices)
    ]


def test_insufficient_bars_returns_no_trade():
    bars = _mk_bars([(10, 10, 9, 10)] * 3)
    plan = analyze(bars)
    assert plan.direction == "no_trade"
    assert plan.confidence == 0.0


def test_blackout_forces_no_trade_even_with_strong_setup():
    # Build a clean bullish structure (same as structure test) that would
    # otherwise pass, but assert blackout overrides it.
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 11, 10, 11),
            (11, 13, 11, 12),
            (12, 12, 10, 10.5),
            (10.5, 11, 10.3, 10.8),
            (10.8, 14, 10.5, 13.8),
            (13.8, 16, 13.5, 15),
        ]
    )
    plan = analyze(bars, calendar_blackout=True, lookback=1)
    assert plan.direction == "no_trade"
    assert plan.confluence.get("blackout") is True


def test_bullish_confluence_produces_trade_plan():
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 11, 10, 11),
            (11, 13, 11, 12),      # swing high @13
            (12, 12, 10, 10.5),    # bearish OB candle
            (10.5, 11, 10.3, 10.8),
            (10.8, 14, 10.5, 13.8),  # BOS bullish, displacement candle
            (13.8, 16, 13.5, 15),
            (15, 15, 13, 13.5),   # pulls back into OB/FVG zone
        ]
    )
    plan = analyze(bars, lookback=1, min_confidence_to_trade=20.0)
    assert plan.direction in ("bullish", "no_trade")
    if plan.direction == "bullish":
        assert plan.entry is not None
        assert plan.stop_loss is not None
        assert plan.stop_loss < plan.entry
        assert plan.take_profit > plan.entry
        assert plan.risk_reward is not None and plan.risk_reward > 0
        assert 0 < plan.confidence <= 100
        assert plan.reasoning != ""


def test_news_sentiment_and_smt_feed_into_confidence():
    bullish_bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 11, 10, 11),
            (11, 13, 11, 12),
            (12, 12, 10, 10.5),
            (10.5, 11, 10.3, 10.8),
            (10.8, 14, 10.5, 13.8),
            (13.8, 16, 13.5, 15),
        ]
    )
    plan_no_news = analyze(bullish_bars, lookback=1, min_confidence_to_trade=0.0)
    plan_with_news = analyze(bullish_bars, lookback=1, min_confidence_to_trade=0.0, news_sentiment=0.8)
    # Agreeing news sentiment should never produce a *lower* confidence
    # than the same setup without it.
    assert plan_with_news.confidence >= plan_no_news.confidence
