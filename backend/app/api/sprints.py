from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.deltas import (
    SnapshotBaseline,
    SnapshotChangeHistoryResponse,
    SnapshotComparisonResponse,
)
from app.schemas.errors import ApiErrorResponse
from app.schemas.issues import SprintIssueListResponse
from app.schemas.sprints import (
    CurrentSprintResponse,
    RecomputeSprintMetricsResponse,
    SprintListResponse,
    SprintMetricsResponse,
    SprintResponse,
)
from app.services.application_errors import ApplicationNotFoundError
from app.services.metric_recompute_service import MetricRecomputeService
from app.services.sprint_response_service import SprintResponseService


router = APIRouter(prefix="/sprints", tags=["sprints"])


@router.get(
    "",
    response_model=SprintListResponse,
    operation_id="get_sprints",
    summary="List sprints",
)
def get_sprints(
    state: str | None = Query(default=None, pattern="^(active|closed|future)$"),
    project_key: str | None = Query(default=None, min_length=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> SprintListResponse:
    return SprintResponseService().list_sprints(
        session=session,
        state=state,
        project_key=project_key,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/current",
    response_model=CurrentSprintResponse,
    operation_id="get_current_sprint",
    summary="Get current sprint",
)
def get_current_sprint(
    project_key: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_db_session),
) -> CurrentSprintResponse:
    return SprintResponseService().get_current_sprint(
        session=session,
        project_key=project_key,
    )


@router.get(
    "/{sprint_id}",
    response_model=SprintResponse,
    operation_id="get_sprint",
    summary="Get sprint",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The sprint was not found.",
        }
    },
)
def get_sprint(
    sprint_id: str,
    session: Session = Depends(get_db_session),
) -> SprintResponse:
    try:
        return SprintResponseService().get_sprint(session=session, sprint_id=sprint_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{sprint_id}/issues",
    response_model=SprintIssueListResponse,
    operation_id="get_sprint_issues",
    summary="List sprint issues",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The sprint was not found.",
        }
    },
)
def get_sprint_issues(
    sprint_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> SprintIssueListResponse:
    try:
        return SprintResponseService().get_sprint_issues(
            session=session,
            sprint_id=sprint_id,
            skip=skip,
            limit=limit,
            current_time=datetime.now(UTC),
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{sprint_id}/metrics",
    response_model=SprintMetricsResponse,
    operation_id="get_sprint_metrics",
    summary="Get sprint metrics",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The sprint was not found.",
        }
    },
)
def get_sprint_metrics(
    sprint_id: str,
    session: Session = Depends(get_db_session),
) -> SprintMetricsResponse:
    try:
        return SprintResponseService().get_sprint_metrics(
            session=session,
            sprint_id=sprint_id,
            current_time=datetime.now(UTC),
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{sprint_id}/snapshot-comparison",
    response_model=SnapshotComparisonResponse,
    operation_id="get_sprint_snapshot_comparison",
    summary="Compare sprint snapshots",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The sprint was not found.",
        }
    },
)
def get_sprint_snapshot_comparison(
    sprint_id: str,
    baseline: SnapshotBaseline = Query(default="previous"),
    session: Session = Depends(get_db_session),
) -> SnapshotComparisonResponse:
    try:
        return SprintResponseService().get_snapshot_comparison(
            session=session,
            sprint_id=sprint_id,
            baseline=baseline,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{sprint_id}/snapshot-change-history",
    response_model=SnapshotChangeHistoryResponse,
    operation_id="get_sprint_snapshot_change_history",
    summary="Get sprint snapshot change history",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The sprint was not found.",
        }
    },
)
def get_sprint_snapshot_change_history(
    sprint_id: str,
    limit: int = Query(default=100, ge=1, le=5000),
    session: Session = Depends(get_db_session),
) -> SnapshotChangeHistoryResponse:
    try:
        return SprintResponseService().get_snapshot_change_history(
            session=session,
            sprint_id=sprint_id,
            limit=limit,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{sprint_id}/recompute",
    response_model=RecomputeSprintMetricsResponse,
    operation_id="recompute_sprint_metrics",
    summary="Recompute sprint metrics",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The sprint was not found.",
        }
    },
)
def recompute_sprint_metrics(
    sprint_id: str,
    session: Session = Depends(get_db_session),
) -> RecomputeSprintMetricsResponse:
    try:
        return MetricRecomputeService().recompute_sprint(
            session=session,
            sprint_id=sprint_id,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
