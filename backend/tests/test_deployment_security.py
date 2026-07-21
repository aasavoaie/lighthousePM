from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pathlib import Path
import pytest

import app.main as main_module
from app.config import get_settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _middleware_classes(app) -> set[type[object]]:
    return {middleware.cls for middleware in app.user_middleware}


def test_desktop_mode_does_not_install_cors_middleware(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "desktop")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("LIGHTHOUSE_CONFIG_FILE", str(tmp_path / "backend.env"))
    monkeypatch.setenv("JIRA_API_TOKEN", "")
    get_settings.cache_clear()

    try:
        app = main_module.create_app()
    finally:
        get_settings.cache_clear()

    assert CORSMiddleware not in _middleware_classes(app)


def test_local_browser_mode_installs_cors_for_explicit_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "local-browser")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:5173")
    get_settings.cache_clear()

    try:
        app = main_module.create_app()
    finally:
        get_settings.cache_clear()

    assert CORSMiddleware in _middleware_classes(app)


def test_invalid_deployment_configuration_stops_before_database_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_initialized = False

    def record_database_initialization() -> None:
        nonlocal database_initialized
        database_initialized = True

    monkeypatch.setenv("DEPLOYMENT_MODE", "desktop")
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("LIGHTHOUSE_CONFIG_FILE", str(tmp_path / "backend.env"))
    monkeypatch.setenv("JIRA_API_TOKEN", "")
    monkeypatch.setattr(main_module, "init_db", record_database_initialization)
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="loopback"):
            with TestClient(main_module.create_app()):
                pass
    finally:
        get_settings.cache_clear()

    assert database_initialized is False


def test_browser_api_token_implementation_has_no_persistent_storage() -> None:
    auth_source = (REPOSITORY_ROOT / "frontend" / "src" / "api" / "auth.ts").read_text(
        encoding="utf-8"
    )

    for forbidden_storage in (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "caches.open",
    ):
        assert forbidden_storage not in auth_source
