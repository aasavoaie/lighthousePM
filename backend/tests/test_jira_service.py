"""Tests for JiraService — uses httpx.MockTransport to avoid network calls."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.services.jira_errors import (
    JiraAuthError,
    JiraRateLimitError,
    JiraRequestError,
    JiraResponseParseError,
)
from app.services.jira_service import JiraService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(**overrides: object) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite:///:memory:",
        jira_base_url="https://test.atlassian.net",
        jira_user_email="test@example.com",
        jira_api_token="token",
        jira_max_retries=0,  # no retries in most tests
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _mock_client(status_code: int, body: object, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    """Return an AsyncClient whose transport always replies with *body*."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            headers=headers or {},
            content=json.dumps(body).encode(),
        )

    return httpx.AsyncClient(
        base_url="https://test.atlassian.net",
        transport=httpx.MockTransport(handler),
    )


def _search_payload(issues: list[dict], next_page_token: str | None = None) -> dict:
    payload: dict = {"isLast": next_page_token is None, "issues": issues}
    if next_page_token is not None:
        payload["nextPageToken"] = next_page_token
    return payload


def _issue_raw(key: str = "PROJ-1") -> dict:
    return {
        "key": key,
        "fields": {
            "summary": "Test issue",
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Alice"},
            "updated": "2026-04-01T10:00:00.000+0000",
            "description": "Some description",
            "labels": ["backend"],
            "components": [{"name": "API"}],
            "reporter": {"displayName": "Bob"},
        },
    }


# ---------------------------------------------------------------------------
# search_issues
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_issues_returns_summaries() -> None:
    client = _mock_client(200, _search_payload([_issue_raw("PROJ-1"), _issue_raw("PROJ-2")]))
    svc = JiraService(client=client, settings=_make_settings())

    issues, next_token = await svc.search_issues("project = PROJ")

    assert len(issues) == 2
    assert issues[0].key == "PROJ-1"
    assert issues[0].status == "In Progress"
    assert issues[0].assignee == "Alice"
    assert next_token is None


@pytest.mark.asyncio
async def test_search_issues_empty_result() -> None:
    client = _mock_client(200, _search_payload([]))
    svc = JiraService(client=client, settings=_make_settings())

    issues, next_token = await svc.search_issues("project = EMPTY")

    assert issues == []
    assert next_token is None


# ---------------------------------------------------------------------------
# get_issue_details
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_issue_details_success() -> None:
    client = _mock_client(200, _issue_raw("PROJ-42"))
    svc = JiraService(client=client, settings=_make_settings())

    detail = await svc.get_issue_details("PROJ-42")

    assert detail.key == "PROJ-42"
    assert detail.summary == "Test issue"
    assert detail.labels == ["backend"]
    assert detail.components == ["API"]
    assert detail.reporter == "Bob"


@pytest.mark.asyncio
async def test_get_issue_details_adf_description() -> None:
    """ADF dict descriptions are collapsed to a placeholder string."""
    raw = _issue_raw("PROJ-1")
    raw["fields"]["description"] = {"type": "doc", "version": 1, "content": []}
    client = _mock_client(200, raw)
    svc = JiraService(client=client, settings=_make_settings())

    detail = await svc.get_issue_details("PROJ-1")

    assert detail.description == "[ADF content]"


@pytest.mark.asyncio
async def test_get_issue_details_uses_custom_mapping_fields() -> None:
    raw = _issue_raw("PROJ-99")
    raw["fields"]["customfield_release"] = [{"name": "Release 9"}]
    raw["fields"]["customfield_severity"] = {"value": "Critical"}
    raw["fields"].pop("priority")
    raw["fields"].pop("fixVersions", None)
    client = _mock_client(200, raw)
    svc = JiraService(
        client=client,
        settings=_make_settings(
            jira_field_release="customfield_release",
            jira_field_severity="customfield_severity",
        ),
    )

    detail = await svc.get_issue_details("PROJ-99")

    assert detail.priority == "Critical"
    assert detail.fix_versions == ["Release 9"]


# ---------------------------------------------------------------------------
# get_issue_changelog
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_issue_changelog_success() -> None:
    payload = {
        "values": [
            {
                "author": {"displayName": "Alice"},
                "created": "2026-03-15T08:00:00.000+0000",
                "items": [
                    {"field": "status", "fromString": "To Do", "toString": "In Progress"},
                    {"field": "assignee", "fromString": None, "toString": "Alice"},
                ],
            }
        ]
    }
    client = _mock_client(200, payload)
    svc = JiraService(client=client, settings=_make_settings())

    entries = await svc.get_issue_changelog("PROJ-1")

    assert len(entries) == 2
    assert entries[0].field_name == "status"
    assert entries[0].from_value == "To Do"
    assert entries[0].author == "Alice"
    assert entries[1].field_name == "assignee"


@pytest.mark.asyncio
async def test_get_issue_changelog_empty() -> None:
    client = _mock_client(200, {"values": []})
    svc = JiraService(client=client, settings=_make_settings())

    entries = await svc.get_issue_changelog("PROJ-1")

    assert entries == []


# ---------------------------------------------------------------------------
# get_project_versions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_project_versions_success() -> None:
    payload = [
        {
            "id": 10001,
            "name": "v1.0",
            "released": True,
            "releaseDate": "2026-05-01",
            "startDate": "2026-04-01",
            "description": "First release",
        }
    ]
    client = _mock_client(200, payload)
    svc = JiraService(client=client, settings=_make_settings())

    versions = await svc.get_project_versions("PROJ")

    assert len(versions) == 1
    assert versions[0].id == "10001"
    assert versions[0].name == "v1.0"
    assert versions[0].released is True
    assert versions[0].project_key == "PROJ"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_401_raises_jira_auth_error() -> None:
    client = _mock_client(401, {"message": "Unauthorized"})
    svc = JiraService(client=client, settings=_make_settings())

    with pytest.raises(JiraAuthError):
        await svc.search_issues("project = PROJ")


@pytest.mark.asyncio
async def test_403_raises_jira_auth_error() -> None:
    client = _mock_client(403, {"message": "Forbidden"})
    svc = JiraService(client=client, settings=_make_settings())

    with pytest.raises(JiraAuthError):
        await svc.search_issues("project = PROJ")


@pytest.mark.asyncio
async def test_429_raises_jira_rate_limit_error() -> None:
    client = _mock_client(429, {}, headers={"Retry-After": "60"})
    svc = JiraService(client=client, settings=_make_settings())

    with pytest.raises(JiraRateLimitError) as exc_info:
        await svc.search_issues("project = PROJ")

    assert exc_info.value.retry_after == 60
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_5xx_exhausts_retries_and_raises() -> None:
    client = _mock_client(503, {"message": "Service Unavailable"})
    svc = JiraService(client=client, settings=_make_settings(jira_max_retries=1))

    with pytest.raises(JiraRequestError) as exc_info:
        await svc.search_issues("project = PROJ")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_network_error_raises_jira_request_error() -> None:
    async def failing_send(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    mock_transport = AsyncMock(spec=httpx.AsyncBaseTransport)
    mock_transport.handle_async_request = failing_send

    client = httpx.AsyncClient(base_url="https://test.atlassian.net", transport=mock_transport)
    svc = JiraService(client=client, settings=_make_settings())

    with pytest.raises(JiraRequestError, match="Network error"):
        await svc.search_issues("project = PROJ")


@pytest.mark.asyncio
async def test_malformed_json_raises_parse_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = httpx.AsyncClient(base_url="https://test.atlassian.net", transport=httpx.MockTransport(handler))
    svc = JiraService(client=client, settings=_make_settings())

    with pytest.raises(JiraResponseParseError):
        await svc.search_issues("project = PROJ")
