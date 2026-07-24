from datetime import datetime
from typing import Literal
import zlib

from app.services.report_chart_renderer import ChartExportService, chart_max_value
from app.services.report_document_models import (
    ChartImage,
    ChartSpec,
    PdfTheme,
    ReportDocument,
    ReportSection,
)
from app.services.report_formatting import format_datetime
from app.services.report_theme import PDFThemeProvider


class SimplePdfRenderer:
    """Render report documents as deterministic PDF 1.4 bytes."""

    page_width = 612
    page_height = 792

    def __init__(
        self,
        generated_at: datetime,
        version: str,
        theme: PdfTheme | None = None,
        chart_export_service: ChartExportService | None = None,
    ) -> None:
        self.generated_at = generated_at
        self.version = version
        self.theme = theme or PDFThemeProvider().theme()
        self.chart_export_service = chart_export_service or ChartExportService(
            theme=self.theme
        )
        self.margin = self.theme.spacing.page_margin
        self.footer_height = self.theme.spacing.footer_height
        self._pages: list[list[str]] = []
        self._content: list[str] = []
        self._y = self.page_height - self.margin
        self._section_index = 0
        self._new_page()

    def render(self, document: ReportDocument) -> bytes:
        self.report_header(document)
        for section in document.sections:
            self.section(section)
        self._finish_page()
        return _build_pdf(self._pages)

    def report_header(self, document: ReportDocument) -> None:
        self._ensure_space(110)
        app_row_center_y = self._y - 10
        self._logo(self.margin, app_row_center_y)
        self._text(
            self.margin + 34,
            app_row_center_y - 4,
            "LighthousePM",
            size=12,
            font=self.theme.typography.heading_font,
            color=self.theme.section.heading.rgb,
        )
        self._y = app_row_center_y - 42
        self.heading(document.title, size=self.theme.typography.title_size)
        self.text(
            document.subtitle,
            size=self.theme.typography.body_size,
            color=self.theme.section.muted.rgb,
        )
        self.text(
            f"Generated {format_datetime(document.generated_at)} | Version {document.version}",
            size=self.theme.typography.small_size + 1,
            color=self.theme.section.muted.rgb,
        )
        self.spacer(14)

    def section(self, section: ReportSection) -> None:
        self._ensure_space(78)
        if self._section_index > 0:
            self._section_divider()
        self._section_index += 1
        self.heading(
            section.title,
            size=self.theme.typography.section_size,
            color=section.heading_color,
        )
        for line in section.lines:
            self.wrapped_text(line)
        if section.rows:
            self.rows(section.rows)
        for bullet in section.bullets:
            self.bullet(bullet)
        for chart in section.charts:
            self.chart(chart)
        self.spacer(self.theme.spacing.section_gap + 12)

    def heading(
        self,
        value: str,
        size: int,
        color: tuple[float, float, float] | None = None,
    ) -> None:
        self._ensure_space(size + 10)
        self._text(
            self.margin,
            self._y,
            value,
            size=size,
            font=self.theme.typography.heading_font,
            color=color or self.theme.section.heading.rgb,
        )
        self._y -= size + 7

    def text(
        self,
        value: str,
        size: int = 10,
        color: tuple[float, float, float] | None = None,
    ) -> None:
        self._ensure_space(size + 6)
        self._text(
            self.margin,
            self._y,
            value,
            size=size,
            color=color or self.theme.section.body.rgb,
        )
        self._y -= size + 5

    def wrapped_text(self, value: str, size: int = 10) -> None:
        for line in _wrap(value, 96):
            self.text(line, size=size)

    def bullet(self, value: str) -> None:
        for index, line in enumerate(_wrap(value, 88)):
            self._ensure_space(15)
            prefix = "- " if index == 0 else "  "
            self._text(self.margin + 8, self._y, f"{prefix}{line}", size=10)
            self._y -= 15

    def rows(self, rows: tuple[tuple[str, str], ...]) -> None:
        key_width = self.theme.table.label_width
        value_x = self.margin + key_width + 10
        for label, value in rows:
            value_lines = _wrap(value, 62)
            row_height = max(18, len(value_lines) * 13 + 4)
            self._ensure_space(row_height)
            self._rect(
                self.margin,
                self._y - row_height + 6,
                self.page_width - 2 * self.margin,
                row_height,
                fill=self.theme.table.background.rgb,
                stroke=self.theme.table.border.rgb,
            )
            self._text(
                self.margin + self.theme.spacing.row_padding,
                self._y - 8,
                label,
                size=9,
                font=self.theme.typography.heading_font,
                color=self.theme.table.label.rgb,
            )
            line_y = self._y - 8
            for value_line in value_lines:
                self._text(
                    value_x,
                    line_y,
                    value_line,
                    size=9,
                    color=self.theme.section.body.rgb,
                )
                line_y -= 13
            self._y -= row_height + 3

    def chart(self, chart: ChartSpec) -> None:
        chart_height = self.theme.spacing.chart_height
        self._ensure_space(chart_height + 50)
        self._text(
            self.margin,
            self._y,
            chart.title,
            size=10,
            font=self.theme.typography.heading_font,
        )
        self._y -= 16
        x = self.margin
        y = self._y - chart_height
        width = self.page_width - 2 * self.margin
        image = self.chart_export_service.export_chart_image(
            chart,
            width=int(width),
            height=chart_height,
        )
        self._image(x, y, width, chart_height, image)
        values = [(label, value) for label, value in chart.points if value is not None]
        if not values:
            self._text(
                x + 16,
                y + chart_height / 2,
                "No chart data available.",
                size=10,
                color=self.theme.section.muted.rgb,
            )
        else:
            self._chart_scale_labels(chart, values, x, y, width, chart_height)
        self._y = y - 28

    def _chart_scale_labels(
        self,
        chart: ChartSpec,
        values: list[tuple[str, float]],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        max_value = chart_max_value(chart, values)
        mid_value = max_value / 2
        plot_left = x + 42
        plot_right = x + width - 24
        plot_bottom = y + 28
        plot_top = y + height - 20
        plot_mid = plot_top - (plot_top - plot_bottom) / 2

        labels = [
            (max_value, plot_top - 3),
            (mid_value, plot_mid - 3),
            (0.0, plot_bottom - 3),
        ]
        for value, label_y in labels:
            self._text(
                x + 4,
                label_y,
                _format_scale_value(value, chart.value_suffix),
                size=7,
                color=self.theme.section.muted.rgb,
            )

        first_label = values[0][0]
        middle_label = values[len(values) // 2][0]
        last_label = values[-1][0]
        self._text(
            plot_left,
            y + 10,
            first_label[:18],
            size=7,
            color=self.theme.section.muted.rgb,
        )
        if len(values) > 2:
            self._text(
                (plot_left + plot_right) / 2 - 28,
                y + 10,
                middle_label[:18],
                size=7,
                color=self.theme.section.muted.rgb,
            )
        self._text(
            plot_right - 70,
            y + 10,
            last_label[:18],
            size=7,
            color=self.theme.section.muted.rgb,
        )

        scale_text = (
            f"Scale: 0{chart.value_suffix} / "
            f"{_format_scale_value(mid_value, chart.value_suffix)} / "
            f"{_format_scale_value(max_value, chart.value_suffix)}"
        )
        self._text(
            plot_left,
            y - 12,
            scale_text,
            size=7,
            color=self.theme.section.muted.rgb,
        )

    def spacer(self, amount: int) -> None:
        self._y -= amount

    def _section_divider(self) -> None:
        self._ensure_space(24)
        self._line(
            self.margin,
            self._y,
            self.page_width - self.margin,
            self._y,
            stroke=self.theme.table.border.rgb,
        )
        self._y -= 18

    def _line_chart(
        self,
        values: list[tuple[str, float]],
        x: float,
        y: float,
        width: float,
        height: float,
        max_value: float,
        color: tuple[float, float, float],
    ) -> None:
        if len(values) == 1:
            px = x + width
            py = y + (values[0][1] / max_value) * height
            self._circle(px, py, 2.5, fill=color)
            return
        points: list[tuple[float, float]] = []
        for index, (_, value) in enumerate(values):
            px = x + (index / (len(values) - 1)) * width
            py = y + (float(value) / max_value) * height
            points.append((px, py))
        self._polyline(points, stroke=color)
        for px, py in points:
            self._circle(px, py, 1.8, fill=color)

    def _bar_chart(
        self,
        values: list[tuple[str, float]],
        x: float,
        y: float,
        width: float,
        height: float,
        max_value: float,
        color: tuple[float, float, float],
    ) -> None:
        bar_gap = 6
        bar_width = max(8, (width - bar_gap * (len(values) - 1)) / len(values))
        for index, (_, value) in enumerate(values):
            bar_height = (float(value) / max_value) * height
            bx = x + index * (bar_width + bar_gap)
            self._rect(bx, y, bar_width, bar_height, fill=color, stroke=color)

    def _ensure_space(self, needed: int) -> None:
        if self._y - needed < self.margin + self.footer_height:
            self._finish_page()
            self._new_page()

    def _new_page(self) -> None:
        self._content = []
        self._y = self.page_height - self.margin

    def _finish_page(self) -> None:
        page_number = len(self._pages) + 1
        footer = (
            f"Generated by LighthousePM | Page {page_number} | "
            f"{format_datetime(self.generated_at)} | Version {self.version}"
        )
        self._text(
            self.margin,
            28,
            footer,
            size=self.theme.typography.small_size,
            color=self.theme.section.muted.rgb,
        )
        self._pages.append(self._content)

    def _text(
        self,
        x: float,
        y: float,
        value: str,
        size: int = 10,
        font: Literal["F1", "F2"] = "F1",
        color: tuple[float, float, float] | None = None,
    ) -> None:
        color = color or self.theme.section.body.rgb
        self._content.append(f"{_pdf_rgb(color)} rg")
        self._content.append(
            f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({_pdf_escape(value)}) Tj ET"
        )

    def _rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        fill: tuple[float, float, float],
        stroke: tuple[float, float, float],
    ) -> None:
        self._content.append(f"{_pdf_rgb(fill)} rg {_pdf_rgb(stroke)} RG")
        self._content.append(
            f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re B"
        )

    def _line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        stroke: tuple[float, float, float],
    ) -> None:
        self._content.append(
            f"{_pdf_rgb(stroke)} RG 1 w "
            f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
        )

    def _polyline(
        self,
        points: list[tuple[float, float]],
        stroke: tuple[float, float, float],
    ) -> None:
        if not points:
            return
        operations = [
            f"{_pdf_rgb(stroke)} RG 2 w "
            f"{points[0][0]:.2f} {points[0][1]:.2f} m"
        ]
        operations.extend(f"{x:.2f} {y:.2f} l" for x, y in points[1:])
        operations.append("S")
        self._content.append(" ".join(operations))

    def _circle(
        self,
        x: float,
        y: float,
        radius: float,
        fill: tuple[float, float, float],
    ) -> None:
        self._content.append(f"{_pdf_rgb(fill)} rg")
        self._content.append(
            f"{x - radius:.2f} {y - radius:.2f} "
            f"{radius * 2:.2f} {radius * 2:.2f} re f"
        )

    def _image(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        image: ChartImage,
    ) -> None:
        compressed_hex = zlib.compress(image.rgb_data).hex()
        self._content.append(
            f"q {width:.2f} 0 0 {height:.2f} {x:.2f} {y:.2f} cm "
            f"BI /W {image.width} /H {image.height} /CS /RGB /BPC 8 /F [/AHx /Fl] "
            f"ID {compressed_hex}> EI Q"
        )

    def _logo(self, x: float, y: float) -> None:
        primary = self.theme.palette["primary"].rgb
        green = self.theme.metric_colors["sprintConfidence"].rgb
        self._rect(
            x,
            y - 11,
            22,
            22,
            fill=self.theme.palette["page"].rgb,
            stroke=primary,
        )
        self._line(x + 5, y - 6, x + 11, y + 5, stroke=primary)
        self._line(x + 11, y + 5, x + 17, y - 6, stroke=green)
        self._circle(x + 11, y + 5, 2, fill=green)


def _pdf_rgb(color: tuple[float, float, float]) -> str:
    return " ".join(
        f"{component:.6f}".rstrip("0").rstrip(".") for component in color
    )


def _format_scale_value(value: float, suffix: str) -> str:
    numeric_value = float(value)
    if numeric_value.is_integer():
        formatted = str(int(numeric_value))
    else:
        formatted = str(round(numeric_value, 2))
    return f"{formatted}{suffix}"


def _wrap(value: str, width: int) -> list[str]:
    words = str(value).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + len(word) + 1 <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _pdf_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{5 + index * 2} 0 R" for index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    for index, content in enumerate(pages):
        page_object_id = 5 + index * 2
        stream_object_id = page_object_id + 1
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {stream_object_id} 0 R >>"
        )
        stream = "\n".join(content).encode("latin-1", errors="replace")
        objects.append(page.encode())
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_at = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n".encode()
    )
    return bytes(output)
