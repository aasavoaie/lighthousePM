from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.errors import ApiErrorResponse
from app.schemas.sync import SyncJiraResponse
from app.services.jira_errors import JiraAuthError
from app.services.sync_service import SyncAlreadyRunningError, SyncService, SyncServiceError

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post(
    "/jira",
    response_model=SyncJiraResponse,
    operation_id="sync_jira",
    summary="Synchronize Jira data",
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Jira synchronization or configuration failed.",
        },
        401: {
            "model": ApiErrorResponse,
            "description": "API bearer or Jira authentication failed.",
        },
        409: {
            "model": ApiErrorResponse,
            "description": "Another Jira synchronization is already running.",
        },
    },
)
async def sync_jira(session: Session = Depends(get_db_session)) -> SyncJiraResponse:
    service = SyncService()
    try:
        result = await service.sync_from_jira(session=session)
    except SyncAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SyncServiceError as exc:
        status_code = 401 if isinstance(exc.__cause__, JiraAuthError) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return SyncJiraResponse.model_validate(result)
