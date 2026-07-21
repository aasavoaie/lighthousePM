from fastapi.testclient import TestClient
import pytest

import app.main as main_module
import app.security as security_module
from app.config import get_settings


def _configured_app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    deployment_mode: str = "local-browser",
    app_env: str = "dev",
    app_host: str = "127.0.0.1",
    api_token: str = "",
    api_token_file: str = "",
):
    monkeypatch.setenv("DEPLOYMENT_MODE", deployment_mode)
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("APP_HOST", app_host)
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "" if deployment_mode == "desktop" else "http://127.0.0.1:5173",
    )
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", api_token)
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN_FILE", api_token_file)
    monkeypatch.setenv("JIRA_API_TOKEN", "")
    monkeypatch.setenv("JIRA_API_TOKEN_FILE", "")
    monkeypatch.setenv("JIRA_SYNC_ENABLED", "false")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", "")
    if deployment_mode == "desktop":
        monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    elif deployment_mode == "docker" or app_env == "prod":
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres@postgres:5432/lighthouse",
        )
        monkeypatch.setenv("POSTGRES_PASSWORD", "test-password")
        monkeypatch.setenv("POSTGRES_PASSWORD_FILE", "")
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "start_scheduler", lambda settings: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)
    get_settings.cache_clear()
    return main_module.create_app()


def test_configured_api_auth_rejects_missing_malformed_and_incorrect_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch, api_token="launch-secret")

    try:
        with TestClient(app) as client:
            responses = [
                client.get("/config/jira"),
                client.get("/config/jira", headers={"Authorization": "Basic launch-secret"}),
                client.get("/config/jira", headers={"Authorization": "Bearer"}),
                client.get("/config/jira", headers={"Authorization": "Bearer wrong-secret"}),
            ]
    finally:
        get_settings.cache_clear()

    for response in responses:
        assert response.status_code == 401
        assert response.json() == {"detail": "API authentication failed."}
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["www-authenticate"] == "Bearer"


def test_health_is_public_and_correct_bearer_token_authorizes_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch, api_token="launch-secret")

    try:
        with TestClient(app) as client:
            health_response = client.get("/health")
            accepted_response = client.get(
                "/config/jira",
                headers={"Authorization": "Bearer launch-secret"},
            )
    finally:
        get_settings.cache_clear()

    assert health_response.status_code == 200
    assert accepted_response.status_code == 200


def test_loopback_development_mode_remains_anonymous_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch)

    try:
        with TestClient(app) as client:
            response = client.get("/config/jira")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200


def test_non_electron_configuration_api_rejects_jira_token_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/config/jira",
                json={"jira_api_token": "submitted-secret"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert "JIRA_API_TOKEN or JIRA_API_TOKEN_FILE" in response.json()["detail"]
    assert "submitted-secret" not in response.text


def test_query_cookie_and_body_values_cannot_authenticate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch, api_token="launch-secret")

    try:
        with TestClient(app) as client:
            query_response = client.get("/config/jira?token=launch-secret")
            client.cookies.set("authorization", "Bearer launch-secret")
            cookie_response = client.get("/config/jira")
            body_response = client.request(
                "POST",
                "/config/jira/test",
                json={"lighthouse_api_token": "launch-secret"},
            )
    finally:
        get_settings.cache_clear()

    assert query_response.status_code == 401
    assert cookie_response.status_code == 401
    assert body_response.status_code == 401


def test_cors_preflight_succeeds_but_cross_origin_data_request_still_requires_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch, api_token="launch-secret")
    origin = "http://127.0.0.1:5173"

    try:
        with TestClient(app) as client:
            preflight_response = client.options(
                "/config/jira",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            protected_response = client.get("/config/jira", headers={"Origin": origin})
    finally:
        get_settings.cache_clear()

    assert preflight_response.status_code == 200
    assert preflight_response.headers["access-control-allow-origin"] == origin
    assert protected_response.status_code == 401
    assert protected_response.headers["access-control-allow-origin"] == origin


def test_file_backed_token_authenticates_without_copying_it_to_direct_setting(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_file = tmp_path / "api-token"
    token_file.write_text("file-secret\n", encoding="utf-8")
    app = _configured_app(monkeypatch, api_token_file=str(token_file))

    try:
        with TestClient(app) as client:
            response = client.get(
                "/config/jira",
                headers={"Authorization": "Bearer file-secret"},
            )
            settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert settings.lighthouse_api_token == ""
    assert settings.effective_lighthouse_api_token == "file-secret"


def test_token_validation_uses_constant_time_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparisons: list[tuple[str, str]] = []

    def compare_digest(provided: str, expected: str) -> bool:
        comparisons.append((provided, expected))
        return provided == expected

    monkeypatch.setattr(security_module.secrets, "compare_digest", compare_digest)
    app = _configured_app(monkeypatch, api_token="launch-secret")

    try:
        with TestClient(app) as client:
            response = client.get(
                "/config/jira",
                headers={"Authorization": "Bearer launch-secret"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert comparisons == [("launch-secret", "launch-secret")]


@pytest.mark.parametrize(
    ("deployment_mode", "app_env", "app_host"),
    [
        ("desktop", "prod", "127.0.0.1"),
        ("local-browser", "prod", "127.0.0.1"),
        ("local-browser", "dev", "0.0.0.0"),
        ("docker", "dev", "0.0.0.0"),
    ],
)
def test_missing_required_token_stops_before_database_and_scheduler_startup(
    monkeypatch: pytest.MonkeyPatch,
    deployment_mode: str,
    app_env: str,
    app_host: str,
) -> None:
    lifecycle_events: list[str] = []
    app = _configured_app(
        monkeypatch,
        deployment_mode=deployment_mode,
        app_env=app_env,
        app_host=app_host,
    )
    monkeypatch.setattr(main_module, "init_db", lambda: lifecycle_events.append("database"))
    monkeypatch.setattr(
        main_module,
        "start_scheduler",
        lambda settings: lifecycle_events.append("scheduler"),
    )

    try:
        with pytest.raises(ValueError, match="LIGHTHOUSE_API_TOKEN"):
            with TestClient(app):
                pass
    finally:
        get_settings.cache_clear()

    assert lifecycle_events == []


@pytest.mark.parametrize("app_host", ["0.0.0.0", "::", "*", "server", "192.0.2.10"])
def test_wildcard_unknown_and_nonloopback_bindings_cannot_bypass_required_authentication(
    monkeypatch: pytest.MonkeyPatch,
    app_host: str,
) -> None:
    app = _configured_app(monkeypatch, app_host=app_host)

    try:
        with pytest.raises(ValueError, match="LIGHTHOUSE_API_TOKEN") as exc_info:
            with TestClient(app):
                pass
    finally:
        get_settings.cache_clear()

    assert "credential" not in str(exc_info.value).casefold()


def test_empty_bind_host_stops_before_database_and_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle_events: list[str] = []
    app = _configured_app(monkeypatch, app_host="")
    monkeypatch.setattr(main_module, "init_db", lambda: lifecycle_events.append("database"))
    monkeypatch.setattr(
        main_module,
        "start_scheduler",
        lambda _settings: lifecycle_events.append("scheduler"),
    )

    try:
        with pytest.raises(ValueError, match="APP_HOST"):
            with TestClient(app):
                pass
    finally:
        get_settings.cache_clear()

    assert lifecycle_events == []
