from typing import Literal

from pydantic import BaseModel


class MetricThresholdMetadataResponse(BaseModel):
    severity: Literal["watch", "critical"]
    comparison: Literal["gt", "gte", "lt", "lte"]
    value: int | float
    meaning: str


class MetricAvailabilityMetadataResponse(BaseModel):
    dependencies: list[str]
    partial_value_policy: Literal[
        "confirmed_minimum",
        "calculated_from_available_data",
        "unavailable",
        "not_supported",
    ]
    supports_not_applicable: bool
    evidence_fields: list[str]
    minimum_coverage_pct: float | None


class MetricDefinitionResponse(BaseModel):
    key: str
    scope: Literal["release", "sprint"]
    api_field: str
    api_location: Literal["metric_values", "response_field", "chart_only"]
    label: str
    description: str
    category: Literal["delivery", "quality", "flow", "risk", "snapshot"]
    unit: Literal["tickets", "events", "percent", "days", "score", "gates"]
    formatting: Literal["integer", "decimal_1", "decimal_2", "decimal_4", "percent_2"]
    display_order: int
    thresholds: list[MetricThresholdMetadataResponse]
    severity_meaning: str
    availability: MetricAvailabilityMetadataResponse
    historical_series: bool
    signal_participation: bool
    confidence_participation: bool
    chart_participation: bool
    report_participation: bool
    ruleset_version: int


class MetricCatalogResponse(BaseModel):
    catalog_version: int
    ruleset_version: int
    release: list[MetricDefinitionResponse]
    sprint: list[MetricDefinitionResponse]
