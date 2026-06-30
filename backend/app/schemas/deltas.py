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
    comparison: SnapshotDeltaComparison


class SnapshotChangeHistoryItem(BaseModel):
    date: datetime
    confidence: float | None
    delta: float | None
    primary_driver: str


class SnapshotChangeHistoryResponse(BaseModel):
    entity_id: str
    items: list[SnapshotChangeHistoryItem]
