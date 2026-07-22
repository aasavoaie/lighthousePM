from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.errors import ApiErrorResponse
from app.services.reporting_service import ReportDepth, ReportingService

router = APIRouter(tags=["reports"])


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _validated_depth(depth: Literal["summary", "full"]) -> ReportDepth:
    return depth


@router.get(
    "/releases/{release_id}/reports/overview.pdf",
    operation_id="export_overview_report_pdf",
    summary="Export overview report PDF",
    response_class=Response,
    responses={
        200: {
            "description": "The overview report PDF attachment.",
            "content": {"application/pdf": {}},
        },
        404: {
            "model": ApiErrorResponse,
            "description": "The release or required report data was not found.",
        },
    },
)
def export_overview_report_pdf(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> Response:
    try:
        pdf = ReportingService().generate_overview_report(
            session=session,
            release_id=release_id,
            generated_at=datetime.now(UTC),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pdf_response(pdf, filename=f"lighthousepm-overview-{release_id}.pdf")


@router.get(
    "/reports/documentation.pdf",
    operation_id="export_documentation_report_pdf",
    summary="Export documentation report PDF",
    response_class=Response,
    responses={
        200: {
            "description": "The product documentation PDF attachment.",
            "content": {"application/pdf": {}},
        },
        404: {
            "model": ApiErrorResponse,
            "description": "The required documentation report data was not found.",
        },
    },
)
def export_documentation_report_pdf() -> Response:
    try:
        pdf = ReportingService().generate_documentation_report(
            generated_at=datetime.now(UTC),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pdf_response(pdf, filename="lighthousepm-documentation.pdf")


@router.get(
    "/releases/{release_id}/reports/{depth}.pdf",
    operation_id="export_release_report_pdf",
    summary="Export release report PDF",
    response_class=Response,
    responses={
        200: {
            "description": "The release report PDF attachment.",
            "content": {"application/pdf": {}},
        },
        404: {
            "model": ApiErrorResponse,
            "description": "The release or required report data was not found.",
        },
    },
)
def export_release_report_pdf(
    release_id: str,
    depth: Literal["summary", "full"],
    session: Session = Depends(get_db_session),
) -> Response:
    try:
        pdf = ReportingService().generate_release_report(
            session=session,
            release_id=release_id,
            depth=_validated_depth(depth),
            generated_at=datetime.now(UTC),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pdf_response(pdf, filename=f"lighthousepm-release-{release_id}-{depth}.pdf")


@router.get(
    "/sprints/{sprint_id}/reports/{depth}.pdf",
    operation_id="export_sprint_report_pdf",
    summary="Export sprint report PDF",
    response_class=Response,
    responses={
        200: {
            "description": "The sprint report PDF attachment.",
            "content": {"application/pdf": {}},
        },
        404: {
            "model": ApiErrorResponse,
            "description": "The sprint or required report data was not found.",
        },
    },
)
def export_sprint_report_pdf(
    sprint_id: str,
    depth: Literal["summary", "full"],
    session: Session = Depends(get_db_session),
) -> Response:
    try:
        pdf = ReportingService().generate_sprint_report(
            session=session,
            sprint_id=sprint_id,
            depth=_validated_depth(depth),
            generated_at=datetime.now(UTC),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pdf_response(pdf, filename=f"lighthousepm-sprint-{sprint_id}-{depth}.pdf")
