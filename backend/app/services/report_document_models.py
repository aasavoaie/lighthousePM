from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal


ReportDepth = Literal["summary", "full"]
RgbColor = tuple[float, float, float]
PdfFontName = Literal["F1", "F2"]


@dataclass(frozen=True)
class PdfColor:
    hex: str
    rgb: RgbColor


@dataclass(frozen=True)
class PdfTypography:
    body_font: PdfFontName
    heading_font: PdfFontName
    title_size: int
    section_size: int
    body_size: int
    small_size: int


@dataclass(frozen=True)
class PdfSpacing:
    page_margin: int
    footer_height: int
    section_gap: int
    row_padding: int
    chart_height: int


@dataclass(frozen=True)
class PdfTableStyle:
    label_width: int
    background: PdfColor
    border: PdfColor
    label: PdfColor


@dataclass(frozen=True)
class PdfSectionStyle:
    heading: PdfColor
    body: PdfColor
    muted: PdfColor
    accent: PdfColor


@dataclass(frozen=True)
class PdfTheme:
    palette: Mapping[str, PdfColor]
    status_colors: Mapping[str, PdfColor]
    confidence_colors: Mapping[str, PdfColor]
    metric_colors: Mapping[str, PdfColor]
    typography: PdfTypography
    spacing: PdfSpacing
    section: PdfSectionStyle
    table: PdfTableStyle

    def __post_init__(self) -> None:
        object.__setattr__(self, "palette", MappingProxyType(dict(self.palette)))
        object.__setattr__(self, "status_colors", MappingProxyType(dict(self.status_colors)))
        object.__setattr__(
            self,
            "confidence_colors",
            MappingProxyType(dict(self.confidence_colors)),
        )
        object.__setattr__(self, "metric_colors", MappingProxyType(dict(self.metric_colors)))


@dataclass(frozen=True, init=False)
class ChartSpec:
    title: str
    kind: Literal["line", "bar"]
    points: tuple[tuple[str, float | None], ...]
    color: RgbColor = (11 / 255, 107 / 255, 203 / 255)
    y_max: float | None = None
    value_suffix: str = ""

    def __init__(
        self,
        title: str,
        kind: Literal["line", "bar"],
        points: Iterable[tuple[str, float | None]],
        color: RgbColor = (11 / 255, 107 / 255, 203 / 255),
        y_max: float | None = None,
        value_suffix: str = "",
    ) -> None:
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "points", tuple(points))
        object.__setattr__(self, "color", color)
        object.__setattr__(self, "y_max", y_max)
        object.__setattr__(self, "value_suffix", value_suffix)


@dataclass(frozen=True)
class ChartImage:
    width: int
    height: int
    rgb_data: bytes


@dataclass(frozen=True, init=False)
class ReportSection:
    title: str
    lines: tuple[str, ...] = ()
    rows: tuple[tuple[str, str], ...] = ()
    bullets: tuple[str, ...] = ()
    charts: tuple[ChartSpec, ...] = ()
    heading_color: RgbColor | None = None

    def __init__(
        self,
        title: str,
        lines: Iterable[str] = (),
        rows: Iterable[tuple[str, str]] = (),
        bullets: Iterable[str] = (),
        charts: Iterable[ChartSpec] = (),
        heading_color: RgbColor | None = None,
    ) -> None:
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "lines", tuple(lines))
        object.__setattr__(self, "rows", tuple(rows))
        object.__setattr__(self, "bullets", tuple(bullets))
        object.__setattr__(self, "charts", tuple(charts))
        object.__setattr__(self, "heading_color", heading_color)


@dataclass(frozen=True, init=False)
class ReportDocument:
    title: str
    subtitle: str
    entity_id: str
    generated_at: datetime
    version: str
    sections: tuple[ReportSection, ...]

    def __init__(
        self,
        title: str,
        subtitle: str,
        entity_id: str,
        generated_at: datetime,
        version: str,
        sections: Iterable[ReportSection],
    ) -> None:
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "subtitle", subtitle)
        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "generated_at", generated_at)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "sections", tuple(sections))
