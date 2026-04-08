from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.sync import SyncJiraResponse
from app.services.sync_service import SyncService, SyncServiceError

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/jira", response_model=SyncJiraResponse)
async def sync_jira(session: Session = Depends(get_db_session)) -> SyncJiraResponse:
    service = SyncService()
    try:
        result = await service.sync_from_jira(session=session)
    except SyncServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SyncJiraResponse.model_validate(result)
