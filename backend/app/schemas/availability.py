from pydantic import BaseModel


class MetricAvailabilityContext(BaseModel):
    has_tickets: bool
    has_story_points: bool
    has_completed_tickets: bool
    has_release_scope: bool
    has_sprint_scope: bool
    has_changelog: bool


class MetricAvailabilityItem(BaseModel):
    available: bool
    reason: str | None
    depends_on: list[str]


class MetricAvailability(BaseModel):
    context: MetricAvailabilityContext
    metrics: dict[str, MetricAvailabilityItem]
