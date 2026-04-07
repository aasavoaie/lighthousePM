"""Jira Cloud API client.

Responsibilities:
- Authenticate with Jira Cloud using HTTP Basic Auth (email + API token).
- Execute requests with configurable timeout and limited retry on 429/5xx.
- Normalize raw Jira JSON into the internal types defined in jira_types.py.
- Map HTTP errors to the domain exceptions defined in jira_errors.py.
"""

import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.services.jira_errors import (
    JiraAuthError,
    JiraRateLimitError,
    JiraRequestError,
    JiraResponseParseError,
)
from app.services.jira_types import (
    JiraChangelogEntry,
    JiraIssueDetail,
    JiraIssueSummary,
    JiraVersion,
)

logger = logging.getLogger(__name__)

_DEFAULT_ISSUE_FIELDS = [
    "summary",
    "status",
    "issuetype",
    "priority",
    "assignee",
    "updated",
    "description",
    "labels",
    "components",
    "reporter",
]


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string from Jira; return None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _display_name(field: dict[str, Any] | None) -> str | None:
    """Extract displayName from a Jira user/priority/status field dict."""
    if field is None:
        return None
    return field.get("displayName") or field.get("name")


def _normalize_issue_summary(raw: dict[str, Any]) -> JiraIssueSummary:
    fields: dict[str, Any] = raw.get("fields", {})
    return JiraIssueSummary(
        key=raw["key"],
        summary=fields.get("summary", ""),
        status=_display_name(fields.get("status")) or "",
        issue_type=_display_name(fields.get("issuetype")) or "",
        priority=_display_name(fields.get("priority")),
        assignee=_display_name(fields.get("assignee")),
        updated=_parse_datetime(fields.get("updated")),
    )


def _normalize_issue_detail(raw: dict[str, Any]) -> JiraIssueDetail:
    fields: dict[str, Any] = raw.get("fields", {})
    labels: list[str] = fields.get("labels") or []
    components: list[str] = [c.get("name", "") for c in (fields.get("components") or [])]
    description_raw = fields.get("description")
    if isinstance(description_raw, dict):
        # Atlassian Document Format — flatten to a single marker; callers can
        # extend this mapping as needed.
        # TODO: implement full ADF-to-text rendering if required.
        description = "[ADF content]"
    else:
        description = description_raw

    return JiraIssueDetail(
        key=raw["key"],
        summary=fields.get("summary", ""),
        status=_display_name(fields.get("status")) or "",
        issue_type=_display_name(fields.get("issuetype")) or "",
        priority=_display_name(fields.get("priority")),
        assignee=_display_name(fields.get("assignee")),
        updated=_parse_datetime(fields.get("updated")),
        description=description,
        labels=labels,
        components=components,
        reporter=_display_name(fields.get("reporter")),
    )


def _normalize_changelog_entry(issue_key: str, history: dict[str, Any]) -> list[JiraChangelogEntry]:
    author = _display_name(history.get("author"))
    changed_at = _parse_datetime(history.get("created")) or datetime.min
    entries: list[JiraChangelogEntry] = []
    for item in history.get("items", []):
        entries.append(
            JiraChangelogEntry(
                issue_key=issue_key,
                field_name=item.get("field", ""),
                from_value=item.get("fromString"),
                to_value=item.get("toString"),
                changed_at=changed_at,
                author=author,
            )
        )
    return entries


class JiraService:
    """Async Jira Cloud API client.

    Pass a pre-built ``httpx.AsyncClient`` to override transport (useful in tests).
    When ``client`` is None the service builds its own client lazily on first use.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._external_client = client
        self._owned_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(
                base_url=self._settings.jira_base_url,
                auth=httpx.BasicAuth(
                    self._settings.jira_user_email,
                    self._settings.jira_api_token,
                ),
                headers={"Accept": "application/json"},
                timeout=self._settings.jira_timeout_seconds,
            )
        return self._owned_client

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an authenticated request with retry on 429 / 5xx."""
        client = self._get_client()
        attempts = self._settings.jira_max_retries + 1
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            logger.debug("Jira %s %s attempt=%d", method.upper(), path, attempt)
            try:
                response = await client.request(method, path, **kwargs)
            except httpx.RequestError as exc:
                logger.warning("Jira network error on %s %s: %s", method.upper(), path, exc)
                last_exc = JiraRequestError(f"Network error contacting Jira: {exc}")
                continue

            logger.debug("Jira %s %s → %d", method.upper(), path, response.status_code)

            if response.status_code in (401, 403):
                raise JiraAuthError(
                    f"Jira authentication failed ({response.status_code}) for {method.upper()} {path}"
                )
            if response.status_code == 429:
                retry_after_raw = response.headers.get("Retry-After")
                retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
                raise JiraRateLimitError(
                    f"Jira rate limit hit for {method.upper()} {path}",
                    retry_after=retry_after,
                )
            if response.status_code >= 500:
                last_exc = JiraRequestError(
                    f"Jira server error {response.status_code} for {method.upper()} {path}",
                    status_code=response.status_code,
                )
                continue
            if not response.is_success:
                raise JiraRequestError(
                    f"Jira returned {response.status_code} for {method.upper()} {path}",
                    status_code=response.status_code,
                )

            try:
                return response.json()
            except Exception as exc:
                raise JiraResponseParseError(
                    f"Could not parse Jira response for {method.upper()} {path}: {exc}"
                ) from exc

        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> list[JiraIssueSummary]:
        """Return issues matching *jql* as lightweight summaries."""
        payload: dict[str, Any] = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": fields or _DEFAULT_ISSUE_FIELDS[:7],  # summary subset for search
        }
        data = await self._request("POST", "/rest/api/3/search", json=payload)
        try:
            return [_normalize_issue_summary(issue) for issue in data.get("issues", [])]
        except (KeyError, TypeError) as exc:
            raise JiraResponseParseError(f"Unexpected search response structure: {exc}") from exc

    async def get_issue_details(
        self,
        issue_key: str,
        fields: list[str] | None = None,
    ) -> JiraIssueDetail:
        """Return full detail for a single issue."""
        params: dict[str, str] = {"fields": ",".join(fields or _DEFAULT_ISSUE_FIELDS)}
        data = await self._request("GET", f"/rest/api/3/issue/{issue_key}", params=params)
        try:
            return _normalize_issue_detail(data)
        except (KeyError, TypeError) as exc:
            raise JiraResponseParseError(
                f"Unexpected issue detail response structure for {issue_key}: {exc}"
            ) from exc

    async def get_issue_changelog(
        self,
        issue_key: str,
        start_at: int = 0,
        max_results: int = 100,
    ) -> list[JiraChangelogEntry]:
        """Return changelog entries for an issue, oldest-first."""
        params: dict[str, Any] = {"startAt": start_at, "maxResults": max_results}
        data = await self._request(
            "GET", f"/rest/api/3/issue/{issue_key}/changelog", params=params
        )
        try:
            entries: list[JiraChangelogEntry] = []
            for history in data.get("values", []):
                entries.extend(_normalize_changelog_entry(issue_key, history))
            return entries
        except (KeyError, TypeError) as exc:
            raise JiraResponseParseError(
                f"Unexpected changelog response structure for {issue_key}: {exc}"
            ) from exc

    async def get_project_versions(self, project_key: str) -> list[JiraVersion]:
        """Return all versions for a Jira project."""
        data = await self._request("GET", f"/rest/api/3/project/{project_key}/versions")
        try:
            versions: list[JiraVersion] = []
            for v in data:
                versions.append(
                    JiraVersion(
                        id=str(v["id"]),
                        name=v.get("name", ""),
                        project_key=project_key,
                        released=bool(v.get("released", False)),
                        release_date=v.get("releaseDate"),
                        start_date=v.get("startDate"),
                        description=v.get("description"),
                    )
                )
            return versions
        except (KeyError, TypeError) as exc:
            raise JiraResponseParseError(
                f"Unexpected versions response structure for project {project_key}: {exc}"
            ) from exc
