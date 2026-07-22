from collections.abc import Iterator

from fastapi.testclient import TestClient
import pytest

import app.main as main_module
from app.config import get_settings
from app.metric_catalog import CATALOG_VERSION, RELEASE_METRICS, SPRINT_METRICS
from app.schemas.metric_metadata import (
    MetricAvailabilityMetadataResponse,
    MetricCatalogResponse,
    MetricDefinitionResponse,
    MetricThresholdMetadataResponse,
)
from app.services.metric_catalog_service import MetricCatalogService
from app.utils.constants import RULESET_VERSION


@pytest.fixture
def authenticated_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DEPLOYMENT_MODE", "local-browser")
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:5173")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", "metadata-secret")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN_FILE", "")
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "start_scheduler", lambda settings: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)
    get_settings.cache_clear()
    app = main_module.create_app()

    try:
        with TestClient(app) as client:
            yield client
    finally:
        get_settings.cache_clear()


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested_value in value.values()
            for nested_key in _nested_keys(nested_value)
        }
    if isinstance(value, list):
        return {
            nested_key
            for nested_value in value
            for nested_key in _nested_keys(nested_value)
        }
    return set()


def test_metric_metadata_requires_authentication_and_returns_versioned_catalog(
    authenticated_client: TestClient,
) -> None:
    unauthenticated = authenticated_client.get("/metadata/metrics")
    authenticated = authenticated_client.get(
        "/metadata/metrics",
        headers={"Authorization": "Bearer metadata-secret"},
    )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.json()["catalog_version"] == CATALOG_VERSION
    assert authenticated.json()["ruleset_version"] == RULESET_VERSION


def test_metric_metadata_serializes_every_definition_in_deterministic_order(
    authenticated_client: TestClient,
) -> None:
    headers = {"Authorization": "Bearer metadata-secret"}
    first_response = authenticated_client.get("/metadata/metrics", headers=headers)
    second_response = authenticated_client.get("/metadata/metrics", headers=headers)
    body = first_response.json()

    assert first_response.status_code == 200
    assert second_response.json() == body
    assert body == MetricCatalogService().get_catalog().model_dump(mode="json")
    assert [metric["key"] for metric in body["release"]] == [
        metric.key for metric in RELEASE_METRICS
    ]
    assert [metric["key"] for metric in body["sprint"]] == [
        metric.key for metric in SPRINT_METRICS
    ]
    assert [metric["display_order"] for metric in body["release"]] == list(
        range(1, len(RELEASE_METRICS) + 1)
    )
    assert body["release"][0]["thresholds"][0] == {
        "severity": "critical",
        "comparison": "gt",
        "value": 0,
        "meaning": "Any open blocker is a hard RED release condition.",
    }


def test_metric_metadata_contains_no_sensitive_configuration(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get(
        "/metadata/metrics",
        headers={"Authorization": "Bearer metadata-secret"},
    )
    body = response.json()

    assert response.status_code == 200
    assert _nested_keys(body).isdisjoint(
        {
            "api_token",
            "database_url",
            "jira_api_token",
            "jira_email",
            "jira_url",
            "password",
            "secret",
        }
    )
    assert "metadata-secret" not in response.text


def test_metric_metadata_openapi_schema_tracks_response_models(
    authenticated_client: TestClient,
) -> None:
    openapi = authenticated_client.app.openapi()
    operation = openapi["paths"]["/metadata/metrics"]["get"]
    response_schema = operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    assert response_schema == {
        "$ref": "#/components/schemas/MetricCatalogResponse"
    }
    for model in (
        MetricCatalogResponse,
        MetricDefinitionResponse,
        MetricAvailabilityMetadataResponse,
        MetricThresholdMetadataResponse,
    ):
        schema = openapi["components"]["schemas"][model.__name__]
        assert set(schema["properties"]) == set(model.model_fields)
        assert set(schema["required"]) == set(model.model_fields)
