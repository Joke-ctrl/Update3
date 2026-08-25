"""
THE MARKET KILL3R V2 — API entrypoint.

Phase 1 (this file): app factory, middleware, routing, health check,
DB startup. AI/SMC/DXY/forecast engines register their own routers here
in later phases without touching this wiring.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.routes import analysis, auth, calendar, health, market, mt5, news, users
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.session import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Auto-create tables only in dev, for convenience. Production/staging
    # must apply schema changes via `alembic upgrade head` explicitly so
    # the DB schema and migration history never drift apart.
    if settings.APP_ENV not in ("production", "staging"):
        init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

    # Health check lives under the versioned prefix (Railway healthcheck target:
    # /api/v1/health) and is also mounted at bare /health for convenience
    # (e.g. simple uptime monitors, the Docker HEALTHCHECK instruction).
    app.include_router(health.router, prefix=settings.API_V1_PREFIX)
    app.include_router(health.router)

    # Versioned API
    app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
    app.include_router(users.router, prefix=settings.API_V1_PREFIX)
    app.include_router(mt5.router, prefix=settings.API_V1_PREFIX)
    app.include_router(analysis.router, prefix=settings.API_V1_PREFIX)
    app.include_router(calendar.router, prefix=settings.API_V1_PREFIX)
    app.include_router(news.router, prefix=settings.API_V1_PREFIX)
    app.include_router(market.router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()


if __name__ == "__main__":
    # Direct `python -m app.main` execution path (in addition to the
    # uvicorn/Procfile/Dockerfile CMD paths), binding explicitly per
    # Railway convention.
    import os

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
    )
