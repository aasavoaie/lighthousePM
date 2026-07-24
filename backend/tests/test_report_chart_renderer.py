import ast
from pathlib import Path

from app.services.report_chart_renderer import ChartExportService, chart_max_value
from app.services.report_document_models import ChartSpec
from app.services.report_theme import PDFThemeProvider
from app.services.reporting_service import ChartExportService as CompatibleChartExportService


SERVICES_DIRECTORY = Path(__file__).resolve().parents[1] / "app" / "services"


def test_chart_renderer_has_no_database_or_pdf_dependencies() -> None:
    source = (SERVICES_DIRECTORY / "report_chart_renderer.py").read_text(
        encoding="utf-8"
    )
    module = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert "sqlalchemy" not in imported_modules
    assert not any(name.startswith("app.repositories") for name in imported_modules)
    assert "app.services.reporting_service" not in imported_modules
    assert not any("pdf_renderer" in name for name in imported_modules)


def test_reporting_service_preserves_chart_renderer_import_compatibility() -> None:
    assert CompatibleChartExportService is ChartExportService


def test_line_bar_and_empty_charts_render_deterministically() -> None:
    theme = PDFThemeProvider().theme()
    renderer = ChartExportService(theme=theme, scale=2)
    points = (("A", 10.0), ("B", 50.0), ("C", 90.0))
    line = ChartSpec(title="Line", kind="line", points=points, y_max=100)
    bar = ChartSpec(title="Bar", kind="bar", points=points, y_max=100)
    empty = ChartSpec(title="Empty", kind="line", points=(("A", None),))

    first_line_image = renderer.export_chart_image(line, width=200, height=80)
    second_line_image = renderer.export_chart_image(line, width=200, height=80)
    bar_image = renderer.export_chart_image(bar, width=200, height=80)
    empty_image = renderer.export_chart_image(empty, width=200, height=80)

    assert first_line_image == second_line_image
    assert first_line_image.rgb_data != bar_image.rgb_data
    assert empty_image.width == 400
    assert empty_image.height == 160
    assert len(empty_image.rgb_data) == empty_image.width * empty_image.height * 3


def test_chart_scale_preserves_explicit_and_data_driven_maximums() -> None:
    data_driven = ChartSpec(
        title="Reopen rate",
        kind="line",
        points=(("A", 80.0), ("B", 125.0)),
    )
    explicit = ChartSpec(
        title="Confidence",
        kind="line",
        points=(("A", 50.0), ("B", 75.0)),
        y_max=100,
    )

    assert chart_max_value(data_driven, data_driven.points) == 125.0
    assert chart_max_value(explicit, explicit.points) == 100.0
