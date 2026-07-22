from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.release_repository import ReleaseRepository
from app.schemas.errors import ApiErrorResponse
from app.schemas.issues import IssueListResponse, IssueResponse
from app.schemas.releases import ReleaseListResponse, ReleaseResponse

router = APIRouter(prefix="/releases", tags=["releases"])


@router.get(
    "",
    response_model=ReleaseListResponse,
    operation_id="get_releases",
    summary="List releases",
)
def get_releases(
    project_key: str | None = Query(default=None, min_length=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> ReleaseListResponse:
    releases, total = ReleaseRepository.list_releases(
        session=session,
        project_key=project_key,
        skip=skip,
        limit=limit,
    )
    return ReleaseListResponse(
        items=[ReleaseResponse.model_validate(release, from_attributes=True) for release in releases],
        skip=skip,
        limit=limit,
        total=total,
    )


@router.get(
    "/{release_id}",
    response_model=ReleaseResponse,
    operation_id="get_release",
    summary="Get release",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The release was not found.",
        }
    },
)
def get_release(release_id: str, session: Session = Depends(get_db_session)) -> ReleaseResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    return ReleaseResponse.model_validate(release, from_attributes=True)


@router.get(
    "/{release_id}/issues",
    response_model=IssueListResponse,
    operation_id="get_release_issues",
    summary="List release issues",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The release was not found.",
        }
    },
)
def get_release_issues(
    release_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> IssueListResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")

    issues, total = ReleaseRepository.list_release_issues(
        session=session,
        release_id=release_id,
        skip=skip,
        limit=limit,
    )
    return IssueListResponse(
        items=[IssueResponse.model_validate(issue, from_attributes=True) for issue in issues],
        skip=skip,
        limit=limit,
        total=total,
    )
