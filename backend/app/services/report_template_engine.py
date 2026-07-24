from datetime import datetime

from app.services.report_data_preparation import (
    PreparedDocumentationReportData,
    PreparedOverviewReportData,
    PreparedReleaseReportData,
    PreparedSprintReportData,
)
from app.services.report_document_models import (
    PdfTheme,
    ReportDepth,
    ReportDocument,
)
from app.services.report_documentation_template import DocumentationReportTemplate
from app.services.report_overview_template import OverviewReportTemplate
from app.services.report_release_template import ReleaseReportTemplate
from app.services.report_sprint_template import SprintReportTemplate
from app.services.report_theme import PDFThemeProvider


class ReportTemplateEngine:
    """Select a focused report template for prepared data."""

    def __init__(self, theme: PdfTheme | None = None) -> None:
        self.theme = theme or PDFThemeProvider().theme()
        self._release_template = ReleaseReportTemplate(theme=self.theme)
        self._sprint_template = SprintReportTemplate(theme=self.theme)
        self._overview_template = OverviewReportTemplate(
            theme=self.theme,
            release_template=self._release_template,
        )
        self._documentation_template = DocumentationReportTemplate()

    def build_release_document(
        self,
        data: PreparedReleaseReportData,
        depth: ReportDepth,
        generated_at: datetime,
    ) -> ReportDocument:
        return self._release_template.build_release_document(
            data=data,
            depth=depth,
            generated_at=generated_at,
        )

    def build_sprint_document(
        self,
        data: PreparedSprintReportData,
        depth: ReportDepth,
        generated_at: datetime,
    ) -> ReportDocument:
        return self._sprint_template.build_sprint_document(
            data=data,
            depth=depth,
            generated_at=generated_at,
        )

    def build_overview_document(
        self,
        data: PreparedOverviewReportData,
        generated_at: datetime,
    ) -> ReportDocument:
        return self._overview_template.build_overview_document(
            data=data,
            generated_at=generated_at,
        )

    def build_documentation_document(
        self,
        data: PreparedDocumentationReportData,
        generated_at: datetime,
    ) -> ReportDocument:
        return self._documentation_template.build_documentation_document(
            data=data,
            generated_at=generated_at,
        )
