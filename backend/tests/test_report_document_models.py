import ast
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.report_document_models import (
    ChartSpec,
    ReportDocument,
    ReportSection,
)
from app.services.report_theme import PDFThemeProvider


SERVICES_DIRECTORY = Path(__file__).resolve().parents[1] / "app" / "services"


def test_document_models_have_no_database_or_rendering_dependencies() -> None:
    source = (SERVICES_DIRECTORY / "report_document_models.py").read_text(
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
    assert not any("renderer" in name for name in imported_modules)


def test_document_collections_are_immutable_and_detached_from_inputs() -> None:
    source_points = [("First", 10.0)]
    source_lines = ["Deterministic report"]
    source_sections: list[ReportSection] = []

    chart = ChartSpec(title="Trend", kind="line", points=source_points)
    section = ReportSection(title="Summary", lines=source_lines, charts=[chart])
    source_sections.append(section)
    document = ReportDocument(
        title="Release report",
        subtitle="LHPM",
        entity_id="REL-1",
        generated_at=datetime(2026, 7, 21, tzinfo=UTC),
        version="1.0.0",
        sections=source_sections,
    )

    source_points.append(("Second", 20.0))
    source_lines.append("Changed outside the model")
    source_sections.clear()

    assert chart.points == (("First", 10.0),)
    assert section.lines == ("Deterministic report",)
    assert section.charts == (chart,)
    assert document.sections == (section,)

    with pytest.raises(FrozenInstanceError):
        chart.title = "Changed"
    with pytest.raises(AttributeError):
        section.lines.append("Changed")
    with pytest.raises(AttributeError):
        document.sections.clear()


def test_theme_color_maps_are_read_only_and_copied() -> None:
    theme = PDFThemeProvider().theme()

    assert theme.palette["primary"].hex == "#0b6bcb"
    assert theme.metric_colors["reopenRate"].hex == "#9f6a00"
    with pytest.raises(TypeError):
        theme.palette["primary"] = theme.palette["red"]
    with pytest.raises(TypeError):
        theme.metric_colors["newMetric"] = theme.palette["green"]
