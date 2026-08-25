"""
Financial news ingestion + sentiment scoring.

CNBC does not offer an authenticated news API, but it does publish real,
public RSS feeds (documented at e.g. rsscatalog.com/CNBC) -- this fetches
those directly. Some cloud provider IPs get bot-detection blocked by
CNBC's edge network; NEWS_RSS_FEEDS is configurable via env so you can
swap in Reuters/MarketWatch/other finance RSS feeds if that happens
without touching code.

Sentiment is scored with a transparent keyword lexicon. It is deterministic,
auditable and does not require an AI key. The optional Anthropic integration
is intentionally reserved for the narrative layer so the market score never
depends on an opaque model call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx

from app.core.config import get_settings

BULLISH_WORDS = {
    "rally", "surge", "soar", "jump", "gain", "gains", "rise", "rises", "rising",
    "bullish", "optimism", "upbeat", "strong", "strength", "beat", "beats",
    "outperform", "record high", "rebound", "recovery", "boost", "upgrade",
}
BEARISH_WORDS = {
    "plunge", "slump", "tumble", "fall", "falls", "falling", "drop", "drops",
    "bearish", "pessimism", "weak", "weakness", "miss", "misses", "underperform",
    "record low", "selloff", "sell-off", "recession", "downgrade", "crash", "slide",
}


@dataclass
class NewsArticle:
    title: str
    link: str
    published: datetime | None
    summary: str
    sentiment: float  # -1 (bearish) .. +1 (bullish)


def _keyword_sentiment(text: str) -> float:
    text_lower = text.lower()
    bull_hits = sum(1 for w in BULLISH_WORDS if w in text_lower)
    bear_hits = sum(1 for w in BEARISH_WORDS if w in text_lower)
    total = bull_hits + bear_hits
    if total == 0:
        return 0.0
    return round((bull_hits - bear_hits) / total, 3)


async def fetch_latest_news(limit_per_feed: int = 10) -> list[NewsArticle]:
    settings = get_settings()
    articles: list[NewsArticle] = []

    async with httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "Mozilla/5.0 (compatible; MarketKill3rBot/2.0)"},
    ) as client:
        for feed_url in settings.NEWS_RSS_FEEDS:
            try:
                response = await client.get(feed_url)
                response.raise_for_status()
            except httpx.HTTPError:
                continue

            parsed = feedparser.parse(response.content)
            for entry in parsed.entries[:limit_per_feed]:
                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")
                published = None
                if getattr(entry, "published_parsed", None):
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                text = f"{title} {summary}"
                articles.append(
                    NewsArticle(
                        title=title,
                        link=getattr(entry, "link", ""),
                        published=published,
                        summary=re.sub("<[^<]+?>", "", summary)[:280],
                        sentiment=_keyword_sentiment(text),
                    )
                )

    return articles


def aggregate_sentiment(articles: list[NewsArticle]) -> float:
    """Simple average sentiment across fetched articles, -1..+1."""
    if not articles:
        return 0.0
    return round(sum(a.sentiment for a in articles) / len(articles), 3)
