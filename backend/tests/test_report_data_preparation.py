import ast
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path

import pytest

from app.repositories.release_repository import ReleaseRepository
from app.repositories.sprint_repository import SprintRepository
from app.services.report_data_preparation import (
    PreparedDocumentationReportData,
    PreparedOverviewReportData,
    PreparedPortfolioData,
    PreparedReleaseReportData,
    PreparedSnapshotComparison,
    PreparedSprintReportData,
    ReportDataPreparationService,
)
from app.services.report_template_engine import (
    ReportTemplateEngine as FocusedReportTemplateEngine,
)
from app.services.reporting_service import ReportTemplateEngine, ReportingService


SERVICES_DIRECTORY = Path(__file__).resolve().parents[1] / "app" / "services"
TEMPLATE_FILENAMES = (
    "report_release_template.py",
    "report_sprint_template.py",
    "report_overview_template.py",
    "report_documentation_template.py",
)
PIPELINE_FILENAMES = (
    "reporting_service.py",
    "report_data_preparation.py",
    "report_template_engine.py",
    "report_template_helpers.py",
    "report_document_models.py",
    "report_chart_renderer.py",
    "report_pdf_renderer.py",
    *TEMPLATE_FILENAMES,
)


def test_data_preparation_has_no_document_or_rendering_dependencies() -> None:
    source = (SERVICES_DIRECTORY / "report_data_preparation.py").read_text(
        encoding="utf-8"
    )
    module = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "app.services.report_document_models" not in imported_modules
    assert "app.services.report_chart_renderer" not in imported_modules
    assert "app.services.report_pdf_renderer" not in imported_modules
    assert "app.services.report_theme" not in imported_modules
    assert "app.services.reporting_service" not in imported_modules


def test_templates_accept_only_prepared_data_and_have_no_data_access_calls() -> None:
    source = inspect.getsource(ReportTemplateEngine)
    forbidden_names = (
        "Repository",
        "RecommendationEngine",
        "SignalService",
        "SnapshotComparisonService",
        "MetricAvailabilityService",
        "JiraFieldMapper",
    )

    assert all(name not in source for name in forbidden_names)
    for method_name in (
        "build_release_document",
        "build_sprint_document",
        "build_overview_document",
        "build_documentation_document",
    ):
        assert "session" not in inspect.signature(
            getattr(ReportTemplateEngine, method_name)
        ).parameters


@pytest.mark.parametrize("filename", TEMPLATE_FILENAMES)
def test_focused_templates_have_no_database_or_service_dependencies(
    filename: str,
) -> None:
    source = (SERVICES_DIRECTORY / filename).read_text(encoding="utf-8")
    module = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "sqlalchemy" not in imported_modules
    assert not any(name.startswith("app.repositories") for name in imported_modules)
    assert "Repository" not in source
    assert "RecommendationEngine" not in source
    assert "SignalService" not in source
    assert "SnapshotComparisonService" not in source


def test_reporting_service_preserves_template_engine_import_compatibility() -> None:
    assert ReportTemplateEngine is FocusedReportTemplateEngine


def test_reporting_facade_requires_explicit_generation_time() -> None:
    for method_name in (
        "generate_release_report",
        "generate_sprint_report",
        "generate_overview_report",
        "generate_documentation_report",
    ):
        parameter = inspect.signature(
            getattr(ReportingService, method_name)
        ).parameters["generated_at"]
        assert parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize("filename", PIPELINE_FILENAMES)
def test_reporting_pipeline_does_not_read_the_system_clock(filename: str) -> None:
    source = (SERVICES_DIRECTORY / filename).read_text(encoding="utf-8")

    assert "datetime.now(" not in source


def test_prepared_documentation_data_is_immutable() -> None:
    prepared = PreparedDocumentationReportData(
        markdown="# Documentation",
        version="1.0.0",
    )

    with pytest.raises(FrozenInstanceError):
        prepared.version = "changed"


@pytest.mark.parametrize(
    "prepared_type",
    (
        PreparedSnapshotComparison,
        PreparedPortfolioData,
        PreparedReleaseReportData,
        PreparedSprintReportData,
        PreparedOverviewReportData,
        PreparedDocumentationReportData,
    ),
)
def test_all_prepared_data_models_are_frozen(prepared_type: type) -> None:
    assert prepared_type.__dataclass_params__.frozen is True


def test_data_preparation_reports_missing_entities_without_http_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ReleaseRepository,
        "get_release_by_id",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        SprintRepository,
        "get_sprint_by_id",
        lambda **_kwargs: None,
    )
    service = ReportDataPreparationService()

    with pytest.raises(ValueError, match="Release 'MISSING' not found"):
        service.prepare_release(session=object(), release_id="MISSING")
    with pytest.raises(ValueError, match="Sprint 'MISSING' not found"):
        service.prepare_sprint(session=object(), sprint_id="MISSING")
