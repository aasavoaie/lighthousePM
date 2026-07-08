from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return basic service health and runtime environment metadata."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.app_env,
    )


@router.get("/ready", response_model=ReadinessResponse)
def get_readiness(session: Session = Depends(get_db_session)) -> ReadinessResponse:
    """Return readiness for serving API requests that depend on storage."""
    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        checks["database"] = "unavailable"
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "service": settings.app_name,
                "environment": settings.app_env,
                "checks": checks,
            },
        ) from exc

    checks["database"] = "ok"
    return ReadinessResponse(
        status="ready",
        service=settings.app_name,
        environment=settings.app_env,
        checks=checks,
    )
