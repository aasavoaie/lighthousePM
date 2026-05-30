from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.issue_repository import IssueRepository
from app.schemas.issues import IssueResponse

router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("/{jira_key}", response_model=IssueResponse)
def get_issue(jira_key: str, session: Session = Depends(get_db_session)) -> IssueResponse:
    issue = IssueRepository.get_issue_by_key(session=session, issue_key=jira_key)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Issue '{jira_key}' not found")
    return IssueResponse.model_validate(issue, from_attributes=True)
