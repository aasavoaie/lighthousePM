from typing import Literal

from pydantic import BaseModel


RecommendationEffort = Literal["low", "medium", "high"]


class RecommendationAction(BaseModel):
    title: str
    description: str
    priority: int
    confidenceImpact: int
    effort: RecommendationEffort
    category: str
