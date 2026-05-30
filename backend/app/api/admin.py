from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
from app.repositories.operational_status_repository import OperationalStatusRepository
from app.schemas.admin import AdminStatusResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/status", response_model=AdminStatusResponse)
def get_admin_status(session: Session = Depends(get_db_session)) -> AdminStatusResponse:
    settings = get_settings()
    status = OperationalStatusRepository.get_status_or_none(session=session)
    if status is None:
        return AdminStatusResponse(
            service=settings.app_name,
            environment=settings.app_env,
            last_sync_succeeded_at=None,
            last_sync_failed_at=None,
            last_sync_failure_summary=None,
            last_metrics_recompute_at=None,
            last_signal_recompute_at=None,
        )

    return AdminStatusResponse(
        service=settings.app_name,
        environment=settings.app_env,
        last_sync_succeeded_at=status.last_sync_succeeded_at,
        last_sync_failed_at=status.last_sync_failed_at,
        last_sync_failure_summary=status.last_sync_failure_summary,
        last_metrics_recompute_at=status.last_metrics_recompute_at,
        last_signal_recompute_at=status.last_signal_recompute_at,
    )
