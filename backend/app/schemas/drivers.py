from pydantic import BaseModel


class DriverAnalysis(BaseModel):
    title: str
    category: str
    impact: float
    contributionPercent: float
    explanation: str
    recommendation: str
