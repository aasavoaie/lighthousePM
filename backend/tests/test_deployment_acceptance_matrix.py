from pathlib import Path

from dotenv import dotenv_values
from fastapi.testclient import TestClient
import pytest

import app.main as main_module
from app.config import get_settings


ACCEPTANCE_MATRIX = (
    ("desktop-prod", "desktop", "prod", "127.0.0.1", True, "direct"),
    ("local-dev-anonymous", "local-browser", "dev", "127.0.0.1", False, "none"),
    ("local-test-anonymous", "local-browser", "test", "localhost", False, "none"),
    ("local-dev-token", "local-browser", "dev", "127.0.0.1", True, "direct"),
    ("local-test-token", "local-browser", "test", "localhost", True, "direct"),
    ("local-prod", "local-browser", "prod", "127.0.0.1", True, "direct"),
    ("local-non-loopback", "local-browser", "dev", "192.0.2.10", True, "direct"),
    ("docker-prod", "docker", "prod", "0.0.0.0", True, "file"),
)


def _configure_scenario(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    deployment_mode: str,
    app_env: str,
    app_host: str,
    token_source: str,
) -> tuple[Path, str]:
    config_file = tmp_path / "config" / "backend.env"
    config_file.parent.mkdir()
    config_file.write_text("# acceptance configuration\nJIRA_SYNC_ENABLED=false\n", encoding="utf-8")
    api_token = "matrix-api-token" if token_source != "none" else ""

    monkeypatch.setenv("LIGHTHOUSE_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("DEPLOYMENT_MODE", deployment_mode)
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("APP_HOST", app_host)
    monkeypatch.setenv("CORS_ORIGINS", "" if deployment_mode == "desktop" else "http://127.0.0.1:5173")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", "")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", "")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN_FILE", "")
    monkeypatch.setenv("JIRA_API_TOKEN", "")
    monkeypatch.setenv("JIRA_API_TOKEN_FILE", "")
    monkeypatch.setenv("JIRA_SYNC_ENABLED", "false")

    if token_source == "direct":
        monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", api_token)
    elif token_source == "file":
        api_token_file = tmp_path / "secrets" / "api-token"
        postgres_password_file = tmp_path / "secrets" / "postgres-password"
        api_token_file.parent.mkdir()
        api_token_file.write_text(f"{api_token}\n", encoding="utf-8")
        postgres_password_file.write_text("matrix-database-password\n", encoding="utf-8")
        monkeypatch.setenv("LIGHTHOUSE_API_TOKEN_FILE", str(api_token_file))
        monkeypatch.setenv("POSTGRES_PASSWORD_FILE", str(postgres_password_file))

    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "start_scheduler", lambda _settings: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)
    get_settings.cache_clear()
    return config_file, api_token


@pytest.mark.parametrize(
    (
        "scenario_name",
        "deployment_mode",
        "app_env",
        "app_host",
        "authentication_required",
        "token_source",
    ),
    ACCEPTANCE_MATRIX,
    ids=[row[0] for row in ACCEPTANCE_MATRIX],
)
def test_supported_deployment_acceptance_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario_name: str,
    deployment_mode: str,
    app_env: str,
    app_host: str,
    authentication_required: bool,
    token_source: str,
) -> None:
    config_file, api_token = _configure_scenario(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        deployment_mode=deployment_mode,
        app_env=app_env,
        app_host=app_host,
        token_source=token_source,
    )
    app = main_module.create_app()
    authorized_headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}

    try:
        with TestClient(app) as client:
            health = client.get("/health")
            anonymous_read = client.get("/config/jira")
            authorized_read = client.get("/config/jira", headers=authorized_headers)
            nonsecret_write = client.put(
                "/config/jira",
                headers=authorized_headers,
                json={"jira_project_key": f"MATRIX-{scenario_name}"},
            )
            token_write = client.put(
                "/config/jira",
                headers=authorized_headers,
                json={"jira_api_token": "candidate-jira-secret"},
            )
    finally:
        get_settings.cache_clear()

    assert health.status_code == 200
    assert set(health.json()) == {"status", "service", "environment"}
    assert "token" not in health.text.casefold()
    assert "password" not in health.text.casefold()
    assert anonymous_read.status_code == (401 if authentication_required else 200)
    assert authorized_read.status_code == 200
    assert nonsecret_write.status_code == 200
    assert nonsecret_write.headers["cache-control"] == "no-store"
    assert dotenv_values(config_file)["JIRA_PROJECT_KEY"] == f"MATRIX-{scenario_name}"

    if deployment_mode == "desktop":
        assert token_write.status_code == 200
        assert token_write.json()["jira_api_token_configured"] is True
    else:
        assert token_write.status_code == 400
        assert "JIRA_API_TOKEN or JIRA_API_TOKEN_FILE" in token_write.json()["detail"]

    for response in (authorized_read, nonsecret_write, token_write):
        assert api_token not in response.text if api_token else True
        assert "candidate-jira-secret" not in response.text
