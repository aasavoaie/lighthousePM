from datetime import datetime

from app.services.report_data_preparation import PreparedDocumentationReportData
from app.services.report_document_models import ReportDocument
from app.services.report_template_helpers import _documentation_sections_from_markdown


class DocumentationReportTemplate:
    def build_documentation_document(
        self,
        data: PreparedDocumentationReportData,
        generated_at: datetime,
    ) -> ReportDocument:
        title, sections = _documentation_sections_from_markdown(data.markdown)
        return ReportDocument(
            title=title,
            subtitle="Product documentation for Overview, Releases, and Sprints",
            entity_id="documentation",
            generated_at=generated_at,
            version=data.version,
            sections=sections,
        )
