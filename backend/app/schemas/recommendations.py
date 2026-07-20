from typing import Literal

from pydantic import BaseModel, Field


RecommendationEffort = Literal["low", "medium", "high"]


class RecommendationAction(BaseModel):
    title: str
    description: str
    priority: int
    confidenceImpact: int
    effort: RecommendationEffort
    category: str
    dataStatus: Literal["COMPUTED", "PARTIAL"] = "COMPUTED"
    explanations: list[str] = Field(default_factory=list)
