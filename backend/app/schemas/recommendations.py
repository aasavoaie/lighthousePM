from typing import Literal

from pydantic import BaseModel, Field


RecommendationEffort = Literal["low", "medium", "high"]
RecommendationDataStatus = Literal["COMPUTED", "PARTIAL"]


class RecommendationAction(BaseModel):
    title: str
    description: str
    priority: int
    confidenceImpact: int
    effort: RecommendationEffort
    category: str
    dataStatus: RecommendationDataStatus = "COMPUTED"
    explanations: list[str] = Field(default_factory=list)
