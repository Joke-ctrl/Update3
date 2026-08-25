"""
Health-check endpoint. Used by Railway (and any uptime monitor) to verify
the service is alive and able to reach its dependencies.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    settings = get_settings()

    # Verify DB connectivity; if this fails the exception propagates as a 500,
    # which is exactly what a deployment healthcheck should catch.
    db.execute(text("SELECT 1"))

    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        version="2.0.0",
        environment=settings.APP_ENV,
    )
