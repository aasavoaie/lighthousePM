from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SnapshotBaseline = Literal["previous", "24h", "7d"]
SnapshotDeltaDirection = Literal["up", "down"]


class SnapshotDeltaContributor(BaseModel):
    metric: str
    delta: float
    impact: float
    direction: SnapshotDeltaDirection


class SnapshotDeltaComparison(BaseModel):
    confidence_delta: float | None = Field(serialization_alias="confidenceDelta")
    contributors: list[SnapshotDeltaContributor]


class SnapshotComparisonResponse(BaseModel):
    entity_id: str
    baseline: SnapshotBaseline
    current_snapshot_at: datetime | None
    baseline_snapshot_at: datetime | None
    has_baseline: bool
    current_ruleset_version: int | None = None
    baseline_ruleset_version: int | None = None
    unavailable_reason: str | None = None
    comparison: SnapshotDeltaComparison


class SnapshotChangeHistoryItem(BaseModel):
    date: datetime
    ruleset_version: int
    version_boundary: bool = False
    confidence: float | None
    delta: float | None
    primary_driver: str
    comparison_unavailable_reason: str | None = None


class SnapshotChangeHistoryResponse(BaseModel):
    entity_id: str
    items: list[SnapshotChangeHistoryItem]
