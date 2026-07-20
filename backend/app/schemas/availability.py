from typing import Literal

from pydantic import BaseModel, Field, model_validator


MetricAvailabilityStatus = Literal["COMPUTED", "PARTIAL", "NOT_COMPUTED", "NOT_APPLICABLE"]


class MetricAvailabilityContext(BaseModel):
    has_tickets: bool
    has_story_points: bool
    has_completed_tickets: bool
    has_release_scope: bool
    has_sprint_scope: bool
    has_changelog: bool


class MetricAvailabilityItem(BaseModel):
    status: MetricAvailabilityStatus
    available: bool
    reason: str | None
    explanations: list[str] = Field(default_factory=list)
    missing_issue_keys: list[str] = Field(default_factory=list)
    depends_on: list[str]

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_item(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        upgraded = dict(value)
        reason = upgraded.get("reason")
        upgraded.setdefault(
            "status",
            "COMPUTED" if upgraded.get("available") else "NOT_COMPUTED",
        )
        upgraded.setdefault("explanations", [reason] if isinstance(reason, str) and reason else [])
        upgraded.setdefault("missing_issue_keys", [])
        return upgraded


class MetricAvailability(BaseModel):
    context: MetricAvailabilityContext
    metrics: dict[str, MetricAvailabilityItem]
