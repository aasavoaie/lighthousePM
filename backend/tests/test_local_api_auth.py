from fastapi.testclient import TestClient

import app.main as main_module
from app.config import get_settings


def test_local_api_auth_rejects_requests_without_launch_token(monkeypatch) -> None:
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", "launch-secret")
    get_settings.cache_clear()
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "start_scheduler", lambda settings: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)

    try:
        with TestClient(main_module.create_app()) as client:
            health_response = client.get("/health")
            rejected_response = client.get("/config/jira")
            accepted_response = client.get("/config/jira", headers={"Authorization": "Bearer launch-secret"})
    finally:
        get_settings.cache_clear()

    assert health_response.status_code == 200
    assert rejected_response.status_code == 401
    assert rejected_response.json() == {"detail": "Local API authentication failed."}
    assert accepted_response.status_code == 200
