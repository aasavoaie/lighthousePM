from collections.abc import Sequence

from app.services.report_document_models import ChartImage, ChartSpec, PdfTheme
from app.services.report_theme import PDFThemeProvider


class ChartExportService:
    """Render report chart specifications into deterministic RGB images."""

    def __init__(self, theme: PdfTheme | None = None, scale: int = 3) -> None:
        self.theme = theme or PDFThemeProvider().theme()
        self.scale = scale

    def export_chart_image(
        self,
        chart: ChartSpec,
        width: int = 516,
        height: int = 150,
    ) -> ChartImage:
        image_width = width * self.scale
        image_height = height * self.scale
        canvas = _RasterCanvas(
            width=image_width,
            height=image_height,
            background=_rgb255(self.theme.palette["page"].rgb),
        )
        values = [(label, value) for label, value in chart.points if value is not None]
        border = _rgb255(self.theme.table.border.rgb)
        muted = _rgb255(self.theme.section.muted.rgb)
        chart_color = _rgb255(chart.color)
        canvas.rect(0, 0, image_width - 1, image_height - 1, outline=border)
        if not values:
            canvas.line(
                28 * self.scale,
                image_height // 2,
                image_width - 28 * self.scale,
                image_height // 2,
                muted,
            )
            return ChartImage(
                width=image_width,
                height=image_height,
                rgb_data=canvas.bytes(),
            )

        max_value = chart_max_value(chart, values)
        plot_left = 42 * self.scale
        plot_right = image_width - 24 * self.scale
        plot_bottom = image_height - 28 * self.scale
        plot_top = 20 * self.scale
        mid_y = plot_top + (plot_bottom - plot_top) // 2
        canvas.line(plot_left, plot_top, plot_right, plot_top, border)
        canvas.line(plot_left, mid_y, plot_right, mid_y, border)
        canvas.line(plot_left, plot_bottom, plot_right, plot_bottom, border)
        canvas.line(plot_left, plot_top, plot_left, plot_bottom, border)

        if chart.kind == "bar":
            self._render_bar_chart(
                canvas,
                values,
                max_value,
                plot_left,
                plot_right,
                plot_top,
                plot_bottom,
                chart_color,
            )
        else:
            self._render_line_chart(
                canvas,
                values,
                max_value,
                plot_left,
                plot_right,
                plot_top,
                plot_bottom,
                chart_color,
            )
        return ChartImage(
            width=image_width,
            height=image_height,
            rgb_data=canvas.bytes(),
        )

    def _render_line_chart(
        self,
        canvas: "_RasterCanvas",
        values: list[tuple[str, float]],
        max_value: float,
        plot_left: int,
        plot_right: int,
        plot_top: int,
        plot_bottom: int,
        color: tuple[int, int, int],
    ) -> None:
        if len(values) == 1:
            x = plot_right
            y = _chart_y(float(values[0][1]), max_value, plot_top, plot_bottom)
            canvas.circle(x, y, max(2, self.scale * 2), color)
            return

        points: list[tuple[int, int]] = []
        plot_width = plot_right - plot_left
        for index, (_, value) in enumerate(values):
            x = plot_left + round((index / (len(values) - 1)) * plot_width)
            y = _chart_y(float(value), max_value, plot_top, plot_bottom)
            points.append((x, y))

        stroke_width = max(2, self.scale * 2)
        for left, right in zip(points, points[1:]):
            canvas.line(
                left[0],
                left[1],
                right[0],
                right[1],
                color,
                width=stroke_width,
            )
        for x, y in points:
            canvas.circle(x, y, max(2, self.scale * 2), color)

    def _render_bar_chart(
        self,
        canvas: "_RasterCanvas",
        values: list[tuple[str, float]],
        max_value: float,
        plot_left: int,
        plot_right: int,
        plot_top: int,
        plot_bottom: int,
        color: tuple[int, int, int],
    ) -> None:
        gap = max(4, 6 * self.scale)
        plot_width = plot_right - plot_left
        bar_width = max(6, (plot_width - gap * (len(values) - 1)) // len(values))
        for index, (_, value) in enumerate(values):
            bar_height = round(
                (float(value) / max_value) * (plot_bottom - plot_top)
            )
            x = plot_left + index * (bar_width + gap)
            canvas.fill_rect(
                x,
                plot_bottom - bar_height,
                min(bar_width, plot_right - x),
                bar_height,
                color,
            )


def chart_max_value(
    chart: ChartSpec,
    values: Sequence[tuple[str, float]],
) -> float:
    numeric_values = [float(value) for _, value in values]
    return max(chart.y_max or max(max(numeric_values), 1.0), 1.0)


class _RasterCanvas:
    def __init__(
        self,
        width: int,
        height: int,
        background: tuple[int, int, int],
    ) -> None:
        self.width = width
        self.height = height
        self._data = bytearray(background * (width * height))

    def bytes(self) -> bytes:
        return bytes(self._data)

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        index = (y * self.width + x) * 3
        self._data[index : index + 3] = bytes(color)

    def fill_rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: tuple[int, int, int],
    ) -> None:
        if width <= 0 or height <= 0:
            return
        left = max(0, x)
        right = min(self.width, x + width)
        top = max(0, y)
        bottom = min(self.height, y + height)
        row = bytes(color) * max(0, right - left)
        for py in range(top, bottom):
            start = (py * self.width + left) * 3
            self._data[start : start + len(row)] = row

    def rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        outline: tuple[int, int, int],
    ) -> None:
        self.line(x, y, x + width, y, outline)
        self.line(x, y + height, x + width, y + height, outline)
        self.line(x, y, x, y + height, outline)
        self.line(x + width, y, x + width, y + height, outline)

    def line(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: tuple[int, int, int],
        width: int = 1,
    ) -> None:
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        error = dx + dy
        x = x1
        y = y1
        radius = max(0, width // 2)
        while True:
            self.fill_rect(x - radius, y - radius, width, width, color)
            if x == x2 and y == y2:
                break
            error2 = 2 * error
            if error2 >= dy:
                error += dy
                x += sx
            if error2 <= dx:
                error += dx
                y += sy

    def circle(
        self,
        x: int,
        y: int,
        radius: int,
        color: tuple[int, int, int],
    ) -> None:
        for py in range(y - radius, y + radius + 1):
            for px in range(x - radius, x + radius + 1):
                if (px - x) ** 2 + (py - y) ** 2 <= radius**2:
                    self.set_pixel(px, py, color)


def _rgb255(color: tuple[float, float, float]) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(component * 255))) for component in color)


def _chart_y(
    value: float,
    max_value: float,
    plot_top: int,
    plot_bottom: int,
) -> int:
    return plot_bottom - round((value / max_value) * (plot_bottom - plot_top))
