from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db_session
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


@router.get("/releases/{release_id}/reports/overview.pdf")
def export_overview_report_pdf(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> Response:
    try:
        pdf = ReportingService().generate_overview_report(session=session, release_id=release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pdf_response(pdf, filename=f"lighthousepm-overview-{release_id}.pdf")


@router.get("/releases/{release_id}/reports/{depth}.pdf")
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pdf_response(pdf, filename=f"lighthousepm-release-{release_id}-{depth}.pdf")


@router.get("/sprints/{sprint_id}/reports/{depth}.pdf")
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pdf_response(pdf, filename=f"lighthousepm-sprint-{sprint_id}-{depth}.pdf")
