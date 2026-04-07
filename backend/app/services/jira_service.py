from typing import Any


class JiraService:
    """Jira API adapter placeholder.

    Real Jira communication and normalization will be implemented in a later step.
    """

    async def fetch_release_issues(self, release_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError("Jira ingestion is not implemented in this scaffold.")
