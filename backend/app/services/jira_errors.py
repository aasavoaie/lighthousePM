"""Exception hierarchy for Jira API errors."""


class JiraServiceError(Exception):
    """Base class for all Jira service errors."""


class JiraAuthError(JiraServiceError):
    """Raised when Jira returns 401 or 403 (bad credentials / insufficient permissions)."""


class JiraRequestError(JiraServiceError):
    """Raised for general HTTP-level failures (non-2xx responses not covered by subclasses)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JiraRateLimitError(JiraRequestError):
    """Raised when Jira returns 429 Too Many Requests."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class JiraResponseParseError(JiraServiceError):
    """Raised when a Jira response cannot be parsed into the expected structure."""
