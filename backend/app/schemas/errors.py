from pydantic import BaseModel


class ApiErrorResponse(BaseModel):
    """Controlled API error returned with a human-readable detail."""

    detail: str
