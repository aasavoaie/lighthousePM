from typing import Literal

from pydantic import BaseModel


ConfidenceStatus = Literal["good", "warning", "critical"]


class ConfidenceBreakdownComponent(BaseModel):
    id: str
    name: str
    score: float
    maxScore: float
    status: ConfidenceStatus
    explanation: str


class ConfidenceBreakdown(BaseModel):
    totalScore: float
    components: list[ConfidenceBreakdownComponent]
