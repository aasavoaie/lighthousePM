from pydantic import ValidationError
from pathlib import Path
import pytest
from sqlalchemy.engine import make_url

from app.config import MAX_SECRET_FILE_BYTES, Settings, get_settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "Jira Release Signals"
    assert settings.app_env == "dev"
    assert settings.deployment_mode == "local-browser"
    assert settings.app_host == "127.0.0.1"
    assert settings.is_loopback_binding is True
    assert settings.app_port == 8000
    assert "://" in settings.database_url
    assert settings.database_echo is False
    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 10
    assert settings.postgres_password == ""
    assert settings.postgres_password_file == ""
    assert settings.lighthouse_api_token == ""
    assert settings.lighthouse_api_token_file == ""
    assert settings.jira_api_token_file == ""
    assert settings.api_token_required is False
    assert settings.api_auth_enabled is False
    assert settings.jira_sync_enabled is False
    assert settings.jira_sync_interval_seconds == 0
    assert settings.jira_field_severity == "priority"
    assert settings.jira_field_release == "fixVersions"
    assert settings.done_statuses == frozenset({"done", "closed", "resolved"})
    assert settings.in_progress_statuses == frozenset(
        {"in progress", "in development", "in review", "in testing"}
    )
    assert settings.high_severity_values == frozenset({"high", "highest", "critical"})
    assert settings.bug_issue_types == frozenset({"bug"})


def test_get_settings_cache() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second


def test_production_rejects_direct_secret_loaded_from_environment_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "backend.env"
    config_file.write_text(
        "APP_ENV=prod\n"
        "DEPLOYMENT_MODE=local-browser\n"
        "APP_HOST=127.0.0.1\n"
        "DATABASE_URL=sqlite+pysqlite:///:memory:\n"
        "LIGHTHOUSE_API_TOKEN=environment-file-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIGHTHOUSE_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("LIGHTHOUSE_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="LIGHTHOUSE_API_TOKEN") as exc_info:
            get_settings()
    finally:
        get_settings.cache_clear()

    assert "environment-file-secret" not in str(exc_info.value)


def test_production_allows_process_secret_with_nonsecret_configuration_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "backend.env"
    config_file.write_text(
        "APP_ENV=prod\n"
        "DEPLOYMENT_MODE=local-browser\n"
        "APP_HOST=127.0.0.1\n"
        "DATABASE_URL=sqlite+pysqlite:///:memory:\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIGHTHOUSE_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", "process-secret")
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    get_settings.cache_clear()

    try:
        settings = get_settings()
        settings.validate_startup_settings()
    finally:
        get_settings.cache_clear()

    assert settings.effective_lighthouse_api_token == "process-secret"


def test_validate_startup_settings_fails_when_required_values_missing() -> None:
    settings = Settings(
        _env_file=None,
        jira_sync_enabled=True,
        jira_base_url="",
        jira_user_email="",
        jira_api_token="",
        jira_project_key="",
        jira_field_severity="",
        jira_field_release="",
        jira_changelog_fix_version_fields="",
    )

    try:
        settings.validate_startup_settings()
        assert False, "Expected ValueError for missing required startup settings"
    except ValueError as exc:
        assert "Missing required Jira startup settings" in str(exc)


def test_validate_startup_settings_skips_validation_when_sync_disabled() -> None:
    settings = Settings(
        _env_file=None,
        jira_sync_enabled=False,
        jira_base_url="",
        jira_user_email="",
        jira_api_token="",
        jira_project_key="",
    )

    settings.validate_startup_settings()


def test_classification_values_are_normalized_and_deduplicated() -> None:
    settings = Settings(
        _env_file=None,
        jira_done_statuses=" Done, CLOSED,done ",
        jira_in_progress_statuses="Building, Review",
        jira_high_severity_values="Sev-1, SEV-1",
        jira_bug_issue_types="Defect, BUG",
    )

    settings.validate_startup_settings()

    assert settings.done_statuses == frozenset({"done", "closed"})
    assert settings.in_progress_statuses == frozenset({"building", "review"})
    assert settings.high_severity_values == frozenset({"sev-1"})
    assert settings.bug_issue_types == frozenset({"defect", "bug"})


def test_classification_validation_runs_when_sync_is_disabled() -> None:
    settings = Settings(
        _env_file=None,
        jira_sync_enabled=False,
        jira_done_statuses="Done,Shared",
        jira_in_progress_statuses="shared,Building",
    )

    try:
        settings.validate_startup_settings()
        assert False, "Expected overlapping status classifications to fail"
    except ValueError as exc:
        assert "must not overlap" in str(exc)


def test_required_classification_sets_must_not_be_empty() -> None:
    settings = Settings(_env_file=None, jira_bug_issue_types=" , ")

    try:
        settings.validate_startup_settings()
        assert False, "Expected an empty Bug classification to fail"
    except ValueError as exc:
        assert "JIRA_BUG_ISSUE_TYPES" in str(exc)


@pytest.mark.parametrize(
    ("deployment_mode", "app_host", "database_url", "cors_origins"),
    [
        ("desktop", "127.0.0.1", "sqlite+pysqlite:///desktop.db", ""),
        (
            "local-browser",
            "localhost",
            "postgresql+psycopg://postgres:postgres@localhost/lighthouse",
            "http://localhost:5173",
        ),
        (
            "docker",
            "0.0.0.0",
            "postgresql+psycopg://postgres@postgres/lighthouse",
            "http://127.0.0.1:5173",
        ),
    ],
)
def test_supported_deployment_modes_validate(
    deployment_mode: str,
    app_host: str,
    database_url: str,
    cors_origins: str,
) -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode=deployment_mode,
        app_host=app_host,
        database_url=database_url,
        cors_origins=cors_origins,
        lighthouse_api_token="test-token",
        postgres_password="test-password" if deployment_mode == "docker" else "",
    )

    settings.validate_startup_settings()


def test_unknown_deployment_mode_is_rejected() -> None:
    with pytest.raises(ValidationError, match="deployment_mode"):
        Settings(_env_file=None, deployment_mode="unknown")


@pytest.mark.parametrize("app_host", ["", "0.0.0.0", "::", "192.168.1.10", "server"])
def test_desktop_deployment_rejects_empty_or_non_loopback_binding(app_host: str) -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="desktop",
        app_host=app_host,
        database_url="sqlite+pysqlite:///desktop.db",
        cors_origins="",
    )

    with pytest.raises(ValueError, match="APP_HOST"):
        settings.validate_startup_settings()


def test_desktop_deployment_requires_sqlite() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="desktop",
        app_host="127.0.0.1",
        database_url="postgresql+psycopg://postgres:postgres@localhost/lighthouse",
        cors_origins="",
    )

    with pytest.raises(ValueError, match="SQLite DATABASE_URL"):
        settings.validate_startup_settings()


def test_desktop_deployment_disables_cors() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="desktop",
        app_host="127.0.0.1",
        database_url="sqlite+pysqlite:///desktop.db",
        cors_origins="http://localhost:5173",
    )

    with pytest.raises(ValueError, match="CORS_ORIGINS to be empty"):
        settings.validate_startup_settings()


@pytest.mark.parametrize(
    "cors_origins",
    [
        "*",
        "http://*.example.com",
        "http://localhost:5173/path",
        "http://localhost:5173/",
        "http://localhost:invalid",
        "http://user:password@localhost:5173",
        "http://localhost:5173?source=test",
        "localhost:5173",
    ],
)
def test_cors_requires_exact_http_or_https_origins(cors_origins: str) -> None:
    settings = Settings(_env_file=None, cors_origins=cors_origins)

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        settings.validate_startup_settings()


@pytest.mark.parametrize(
    ("deployment_mode", "app_env", "app_host", "required"),
    [
        ("local-browser", "dev", "127.0.0.1", False),
        ("local-browser", "test", "localhost", False),
        ("local-browser", "prod", "127.0.0.1", True),
        ("local-browser", "dev", "0.0.0.0", True),
        ("local-browser", "test", "192.168.1.10", True),
        ("desktop", "dev", "127.0.0.1", True),
        ("desktop", "prod", "localhost", True),
        ("docker", "dev", "0.0.0.0", True),
        ("docker", "test", "127.0.0.1", True),
    ],
)
def test_api_token_requirement_matrix(
    deployment_mode: str,
    app_env: str,
    app_host: str,
    required: bool,
) -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode=deployment_mode,
        app_env=app_env,
        app_host=app_host,
    )

    assert settings.api_token_required is required


@pytest.mark.parametrize(
    ("deployment_mode", "app_env", "app_host"),
    [
        ("local-browser", "prod", "127.0.0.1"),
        ("local-browser", "dev", "0.0.0.0"),
        ("desktop", "prod", "127.0.0.1"),
        ("docker", "dev", "0.0.0.0"),
    ],
)
def test_required_api_token_is_validated_before_startup(
    deployment_mode: str,
    app_env: str,
    app_host: str,
) -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode=deployment_mode,
        app_env=app_env,
        app_host=app_host,
        database_url=(
            "sqlite+pysqlite:///test.db"
            if deployment_mode == "desktop"
            else (
                "postgresql+psycopg://postgres@localhost/lighthouse"
                if app_env == "prod" or deployment_mode == "docker"
                else "postgresql+psycopg://postgres:postgres@localhost/lighthouse"
            )
        ),
        postgres_password=(
            "test-password" if app_env == "prod" or deployment_mode == "docker" else ""
        ),
        cors_origins="" if deployment_mode == "desktop" else "http://localhost:5173",
    )

    with pytest.raises(ValueError, match="LIGHTHOUSE_API_TOKEN"):
        settings.validate_startup_settings()


def test_optional_loopback_development_token_enables_auth_without_changing_its_value() -> None:
    settings = Settings(_env_file=None, lighthouse_api_token=" token with spaces ")

    settings.validate_startup_settings()

    assert settings.api_auth_enabled is True
    assert settings.effective_lighthouse_api_token == " token with spaces "


def test_api_token_file_is_loaded_once_and_removes_one_trailing_line_ending(tmp_path) -> None:
    token_file = tmp_path / "api-token"
    token_file.write_bytes(b"file-token\r\n")
    settings = Settings(_env_file=None, lighthouse_api_token_file=str(token_file))

    settings.validate_startup_settings()
    token_file.write_text("changed-token", encoding="utf-8")

    assert settings.effective_lighthouse_api_token == "file-token"


def test_direct_and_file_api_tokens_conflict(tmp_path) -> None:
    token_file = tmp_path / "api-token"
    token_file.write_text("file-token", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        lighthouse_api_token="direct-token",
        lighthouse_api_token_file=str(token_file),
    )

    with pytest.raises(ValueError, match="cannot both be configured"):
        settings.validate_startup_settings()


@pytest.mark.parametrize("file_contents", [b"", b" \n", b"x" * (MAX_SECRET_FILE_BYTES + 1)])
def test_invalid_api_token_file_content_is_rejected(tmp_path, file_contents: bytes) -> None:
    token_file = tmp_path / "api-token"
    token_file.write_bytes(file_contents)
    settings = Settings(_env_file=None, lighthouse_api_token_file=str(token_file))

    with pytest.raises(ValueError, match="LIGHTHOUSE_API_TOKEN_FILE"):
        settings.validate_startup_settings()


def test_missing_api_token_file_is_rejected_without_exposing_its_path(tmp_path) -> None:
    token_file = tmp_path / "private-token-name"
    settings = Settings(_env_file=None, lighthouse_api_token_file=str(token_file))

    with pytest.raises(ValueError, match="LIGHTHOUSE_API_TOKEN_FILE") as exc_info:
        settings.validate_startup_settings()

    assert str(token_file) not in str(exc_info.value)


def test_jira_token_file_is_loaded_once_and_removes_one_trailing_line_ending(tmp_path) -> None:
    token_file = tmp_path / "jira-token"
    token_file.write_bytes(b"jira-file-token\n")
    settings = Settings(
        _env_file=None,
        jira_sync_enabled=True,
        jira_base_url="https://example.atlassian.net",
        jira_user_email="user@example.com",
        jira_api_token_file=str(token_file),
        jira_project_key="LHPM",
    )

    settings.validate_startup_settings()
    token_file.write_text("changed-token", encoding="utf-8")

    assert settings.effective_jira_api_token == "jira-file-token"


def test_direct_and_file_jira_tokens_conflict(tmp_path) -> None:
    token_file = tmp_path / "jira-token"
    token_file.write_text("file-token", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        jira_api_token="direct-token",
        jira_api_token_file=str(token_file),
    )

    with pytest.raises(ValueError, match="JIRA_API_TOKEN and JIRA_API_TOKEN_FILE"):
        settings.validate_startup_settings()


@pytest.mark.parametrize(
    "file_contents",
    [b"", b" \r\n", b"x" * (MAX_SECRET_FILE_BYTES + 1), b"\xff"],
)
def test_invalid_jira_token_file_is_rejected_without_exposing_content(
    tmp_path,
    file_contents: bytes,
) -> None:
    token_file = tmp_path / "private-jira-token"
    token_file.write_bytes(file_contents)
    settings = Settings(_env_file=None, jira_api_token_file=str(token_file))

    with pytest.raises(ValueError, match="JIRA_API_TOKEN_FILE") as exc_info:
        settings.validate_startup_settings()

    assert str(token_file) not in str(exc_info.value)
    if len(file_contents) >= 128:
        assert file_contents[:128].decode("utf-8", errors="ignore") not in str(exc_info.value)


def test_secret_file_symlink_is_rejected(tmp_path) -> None:
    target = tmp_path / "jira-token-target"
    target.write_text("file-token", encoding="utf-8")
    link = tmp_path / "jira-token-link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks requires additional privileges on this platform")
    settings = Settings(_env_file=None, jira_api_token_file=str(link))

    with pytest.raises(ValueError, match="readable regular file"):
        settings.validate_startup_settings()


def test_unreadable_secret_file_is_rejected_without_exposing_path(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_file = tmp_path / "unreadable-jira-token"
    token_file.write_text("secret", encoding="utf-8")
    original_read_text = Path.read_text

    def deny_selected_file(path: Path, *args, **kwargs) -> str:
        if path == token_file:
            raise PermissionError("synthetic permission denial")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_selected_file)
    settings = Settings(_env_file=None, jira_api_token_file=str(token_file))

    with pytest.raises(ValueError, match="JIRA_API_TOKEN_FILE") as exc_info:
        settings.validate_startup_settings()

    assert str(token_file) not in str(exc_info.value)


def test_postgres_password_file_builds_database_url_in_memory(tmp_path) -> None:
    password_file = tmp_path / "postgres-password"
    password_file.write_text("p@ss word/with:symbols\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        app_env="prod",
        database_url="postgresql+psycopg://operator@database:5432/lighthouse",
        postgres_password_file=str(password_file),
        lighthouse_api_token="api-token",
    )

    settings.validate_startup_settings()
    password_file.write_text("changed", encoding="utf-8")

    effective_url = make_url(settings.effective_database_url)
    assert effective_url.password == "p@ss word/with:symbols"
    assert settings.database_url == "postgresql+psycopg://operator@database:5432/lighthouse"
    assert settings.postgres_password == ""


def test_direct_and_file_postgres_passwords_conflict(tmp_path) -> None:
    password_file = tmp_path / "postgres-password"
    password_file.write_text("file-password", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        postgres_password="direct-password",
        postgres_password_file=str(password_file),
    )

    with pytest.raises(ValueError, match="POSTGRES_PASSWORD and POSTGRES_PASSWORD_FILE"):
        settings.validate_startup_settings()


@pytest.mark.parametrize("deployment_mode,app_env", [("docker", "dev"), ("local-browser", "prod")])
def test_embedded_postgres_password_is_rejected_in_secure_modes(
    deployment_mode: str,
    app_env: str,
) -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode=deployment_mode,
        app_env=app_env,
        app_host="0.0.0.0" if deployment_mode == "docker" else "127.0.0.1",
        database_url="postgresql+psycopg://operator:must-not-embed@database/lighthouse",
        lighthouse_api_token="api-token",
    )

    with pytest.raises(ValueError, match="must not be embedded") as exc_info:
        settings.validate_startup_settings()

    assert "must-not-embed" not in str(exc_info.value)


def test_loopback_development_retains_legacy_embedded_postgres_password() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="local-browser",
        app_env="dev",
        app_host="127.0.0.1",
        database_url="postgresql+psycopg://operator:development-only@localhost/lighthouse",
    )

    settings.validate_startup_settings()

    assert make_url(settings.effective_database_url).password == "development-only"


def test_invalid_database_url_error_does_not_echo_credential_material() -> None:
    settings = Settings(
        _env_file=None,
        database_url="not a valid URL containing database-secret",
    )

    with pytest.raises(ValueError, match="DATABASE_URL") as exc_info:
        settings.validate_startup_settings()

    assert "database-secret" not in str(exc_info.value)
