from app.services.report_document_models import (
    PdfColor,
    PdfSectionStyle,
    PdfSpacing,
    PdfTableStyle,
    PdfTheme,
    PdfTypography,
)


class PDFThemeProvider:
    """Provide the LighthousePM PDF palette and layout tokens."""

    def theme(self) -> PdfTheme:
        palette = {
            "text": pdf_color("#122033"),
            "muted": pdf_color("#58677c"),
            "label": pdf_color("#304a68"),
            "border": pdf_color("#d6e0ea"),
            "table_background": pdf_color("#f6f9fc"),
            "page": pdf_color("#ffffff"),
            "primary": pdf_color("#0b6bcb"),
            "green": pdf_color("#237445"),
            "amber": pdf_color("#e48f00"),
            "risk_amber": pdf_color("#9f6a00"),
            "red": pdf_color("#c43c2d"),
            "purple": pdf_color("#6f42c1"),
        }
        return PdfTheme(
            palette=palette,
            status_colors={
                "GREEN": palette["green"],
                "YELLOW": palette["amber"],
                "RED": palette["red"],
                "good": palette["green"],
                "warning": palette["amber"],
                "critical": palette["red"],
            },
            confidence_colors={
                "high": palette["green"],
                "medium": palette["amber"],
                "low": palette["red"],
            },
            metric_colors={
                "blockers": palette["red"],
                "bugs": palette["amber"],
                "scopeCompleted": palette["primary"],
                "completedTickets": palette["green"],
                "scopeChurn": palette["purple"],
                "cycleTime": palette["green"],
                "reopenRate": palette["risk_amber"],
                "sprintConfidence": palette["green"],
                "confidenceWatch": palette["amber"],
                "confidenceRisk": palette["risk_amber"],
                "confidenceCritical": palette["red"],
                "progressAlignment": palette["primary"],
                "velocityFit": palette["purple"],
                "blockerHealth": palette["green"],
                "scopeStability": palette["risk_amber"],
                "readiness": palette["primary"],
                "gatesPassed": palette["green"],
                "neutralRisk": pdf_color("#58677c"),
                "committedScope": palette["primary"],
                "completedScope": palette["green"],
                "releasedStoryPoints": palette["primary"],
                "unreleasedStoryPoints": palette["amber"],
                "closedSprintStoryPoints": palette["primary"],
                "notClosedSprintStoryPoints": palette["amber"],
            },
            typography=PdfTypography(
                body_font="F1",
                heading_font="F2",
                title_size=20,
                section_size=14,
                body_size=10,
                small_size=8,
            ),
            spacing=PdfSpacing(
                page_margin=48,
                footer_height=32,
                section_gap=8,
                row_padding=8,
                chart_height=150,
            ),
            section=PdfSectionStyle(
                heading=palette["text"],
                body=palette["text"],
                muted=palette["muted"],
                accent=palette["primary"],
            ),
            table=PdfTableStyle(
                label_width=170,
                background=palette["table_background"],
                border=palette["border"],
                label=palette["label"],
            ),
        )

    def confidence_color(self, confidence_score: float | None) -> PdfColor:
        theme = self.theme()
        if confidence_score is None:
            return theme.palette["muted"]
        if confidence_score >= 91:
            return theme.confidence_colors["high"]
        if confidence_score >= 61:
            return theme.confidence_colors["medium"]
        return theme.confidence_colors["low"]


def pdf_color(hex_value: str) -> PdfColor:
    normalized = hex_value.strip().lstrip("#")
    if len(normalized) != 6:
        raise ValueError(f"Invalid PDF color '{hex_value}'")
    red = int(normalized[0:2], 16) / 255
    green = int(normalized[2:4], 16) / 255
    blue = int(normalized[4:6], 16) / 255
    return PdfColor(hex=f"#{normalized.lower()}", rgb=(red, green, blue))
