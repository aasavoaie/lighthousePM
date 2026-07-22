from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal, Mapping


ReportDepth = Literal["summary", "full"]
RgbColor = tuple[float, float, float]


@dataclass(frozen=True)
class PdfColor:
    hex: str
    rgb: RgbColor


@dataclass(frozen=True)
class PdfTypography:
    body_font: str
    heading_font: str
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


@dataclass(frozen=True)
class ChartSpec:
    title: str
    kind: Literal["line", "bar"]
    points: tuple[tuple[str, float | None], ...]
    color: RgbColor = (11 / 255, 107 / 255, 203 / 255)
    y_max: float | None = None
    value_suffix: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", tuple(self.points))


@dataclass(frozen=True)
class ChartImage:
    width: int
    height: int
    rgb_data: bytes


@dataclass(frozen=True)
class ReportSection:
    title: str
    lines: tuple[str, ...] = field(default_factory=tuple)
    rows: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    bullets: tuple[str, ...] = field(default_factory=tuple)
    charts: tuple[ChartSpec, ...] = field(default_factory=tuple)
    heading_color: RgbColor | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", tuple(self.lines))
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "bullets", tuple(self.bullets))
        object.__setattr__(self, "charts", tuple(self.charts))


@dataclass(frozen=True)
class ReportDocument:
    title: str
    subtitle: str
    entity_id: str
    generated_at: datetime
    version: str
    sections: tuple[ReportSection, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sections", tuple(self.sections))
