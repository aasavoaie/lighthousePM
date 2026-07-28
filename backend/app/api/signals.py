from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.errors import ApiErrorResponse
from app.schemas.signals import ReleaseSignalResponse
from app.services.application_errors import ApplicationNotFoundError
from app.services.release_signal_response_service import ReleaseSignalResponseService

router = APIRouter(prefix="/releases", tags=["signals"])


@router.get(
    "/{release_id}/signal",
    response_model=ReleaseSignalResponse,
    operation_id="get_release_signal",
    summary="Get release signal",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The release was not found.",
        }
    },
)
def get_release_signal(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> ReleaseSignalResponse:
    try:
        return ReleaseSignalResponseService().get_signal(
            session=session,
            release_id=release_id,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
