from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.sync import SyncJiraResponse
from app.services.jira_errors import JiraAuthError
from app.services.sync_service import SyncAlreadyRunningError, SyncService, SyncServiceError

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/jira", response_model=SyncJiraResponse)
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
