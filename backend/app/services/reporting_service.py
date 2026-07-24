from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.services.report_chart_renderer import ChartExportService
from app.services.report_data_preparation import ReportDataPreparationService
from app.services.report_document_models import ChartSpec, ReportDepth
from app.services.report_pdf_renderer import SimplePdfRenderer
from app.services.report_template_engine import ReportTemplateEngine
from app.services.report_theme import PDFThemeProvider, pdf_color


__all__ = [
    "ChartExportService",
    "ChartSpec",
    "PDFThemeProvider",
    "ReportDepth",
    "ReportTemplateEngine",
    "ReportingService",
    "SimplePdfRenderer",
    "pdf_color",
]


class ReportingService:
    """Builds stakeholder PDF reports from deterministic LighthousePM data."""

    def __init__(
        self,
        template_engine: ReportTemplateEngine | None = None,
        theme_provider: PDFThemeProvider | None = None,
        chart_export_service: ChartExportService | None = None,
        data_preparation_service: ReportDataPreparationService | None = None,
    ) -> None:
        self._theme_provider = theme_provider or PDFThemeProvider()
        self._theme = self._theme_provider.theme()
        self._template_engine = template_engine or ReportTemplateEngine(theme=self._theme)
        self._chart_export_service = chart_export_service or ChartExportService(theme=self._theme)
        self._data_preparation_service = (
            data_preparation_service or ReportDataPreparationService()
        )

    def generate_release_report(
        self,
        *,
        session: Session,
        release_id: str,
        depth: ReportDepth,
        generated_at: datetime,
    ) -> bytes:
        data = self._data_preparation_service.prepare_release(
            session=session,
            release_id=release_id,
        )
        document = self._template_engine.build_release_document(data, depth, generated_at)
        return SimplePdfRenderer(
            generated_at=generated_at,
            version=document.version,
            theme=self._theme,
            chart_export_service=self._chart_export_service,
        ).render(document)

    def generate_sprint_report(
        self,
        *,
        session: Session,
        sprint_id: str,
        depth: ReportDepth,
        generated_at: datetime,
    ) -> bytes:
        data = self._data_preparation_service.prepare_sprint(
            session=session,
            sprint_id=sprint_id,
        )
        document = self._template_engine.build_sprint_document(data, depth, generated_at)
        return SimplePdfRenderer(
            generated_at=generated_at,
            version=document.version,
            theme=self._theme,
            chart_export_service=self._chart_export_service,
        ).render(document)

    def generate_overview_report(
        self,
        *,
        session: Session,
        release_id: str,
        generated_at: datetime,
    ) -> bytes:
        data = self._data_preparation_service.prepare_overview(
            session=session,
            release_id=release_id,
        )
        document = self._template_engine.build_overview_document(data, generated_at)
        return SimplePdfRenderer(
            generated_at=generated_at,
            version=document.version,
            theme=self._theme,
            chart_export_service=self._chart_export_service,
        ).render(document)

    def generate_documentation_report(self, *, generated_at: datetime) -> bytes:
        data = self._data_preparation_service.prepare_documentation()
        document = self._template_engine.build_documentation_document(data, generated_at)
        return SimplePdfRenderer(
            generated_at=generated_at,
            version=document.version,
            theme=self._theme,
            chart_export_service=self._chart_export_service,
        ).render(document)
