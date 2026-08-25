"""
Financial news endpoints (see app/services/news_service.py).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.news_service import aggregate_sentiment, fetch_latest_news

router = APIRouter(prefix="/news", tags=["news"])


class NewsArticleOut(BaseModel):
    title: str
    link: str
    published: str | None
    summary: str
    sentiment: float


class NewsFeedOut(BaseModel):
    articles: list[NewsArticleOut]
    aggregate_sentiment: float


@router.get("/latest", response_model=NewsFeedOut)
async def latest_news(current_user: User = Depends(get_current_user)) -> NewsFeedOut:
    articles = await fetch_latest_news()
    return NewsFeedOut(
        articles=[
            NewsArticleOut(
                title=a.title,
                link=a.link,
                published=a.published.isoformat() if a.published else None,
                summary=a.summary,
                sentiment=a.sentiment,
            )
            for a in articles
        ],
        aggregate_sentiment=aggregate_sentiment(articles),
    )
