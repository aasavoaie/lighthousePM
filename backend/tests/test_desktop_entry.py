import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL

from app.config import Settings
from app.db.session import create_database_engine
from desktop_entry import _load_optional_env_file, _parse_args, _sqlite_url, main


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "20260407_0001"


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIRECTORY / "alembic"))
    return config


def _current_head() -> str:
    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


def _database_url(database_path: Path) -> str:
    return URL.create(
        drivername="sqlite+pysqlite",
        database=str(database_path),
    ).render_as_string(hide_password=False)


def _create_source_database(database_path: Path) -> None:
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_database_url(database_path))
    )
    config = _alembic_config()
    try:
        with database_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, SOURCE_REVISION)
            connection.execute(
                text(
                    "INSERT INTO releases "
                    "(release_id, name, project_key, status) "
                    "VALUES ('utility-sentinel', 'Utility sentinel', 'UTL', 'unreleased')"
                )
            )
    finally:
        database_engine.dispose()


def test_sqlite_url_uses_absolute_forward_slash_path(tmp_path: Path) -> None:
    database_path = tmp_path / "local data" / "lighthouse.db"

    database_url = _sqlite_url(database_path)

    assert database_url == f"sqlite+pysqlite:///{database_path.resolve().as_posix()}"


def test_optional_env_file_loads_values_without_overriding_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "backend.env"
    env_file.write_text(
        "LIGHTHOUSE_TEST_EXISTING=FROM_FILE\nLIGHTHOUSE_TEST_NEW=FROM_FILE\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIGHTHOUSE_TEST_EXISTING", "FROM_PROCESS")
    monkeypatch.delenv("LIGHTHOUSE_TEST_NEW", raising=False)

    _load_optional_env_file(env_file)

    assert os.environ["LIGHTHOUSE_TEST_EXISTING"] == "FROM_PROCESS"
    assert os.environ["LIGHTHOUSE_TEST_NEW"] == "FROM_FILE"


def test_server_arguments_remain_compatible() -> None:
    args = _parse_args(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "8123",
            "--database-path",
            "local.db",
            "--app-env",
            "test",
        ]
    )

    assert args.host == "127.0.0.1"
    assert args.port == 8123
    assert args.database_path == Path("local.db")
    assert args.app_env == "test"


def test_server_start_declares_desktop_mode_and_effective_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def run_uvicorn(app_import: str, **kwargs: object) -> None:
        captured["app_import"] = app_import
        captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=run_uvicorn))
    for setting_name in (
        "APP_ENV",
        "DEPLOYMENT_MODE",
        "APP_HOST",
        "APP_PORT",
        "DATABASE_URL",
        "CORS_ORIGINS",
        "LOG_LEVEL",
        "LIGHTHOUSE_CONFIG_FILE",
    ):
        monkeypatch.setenv(setting_name, "previous-test-value")
    database_path = tmp_path / "data" / "lighthouse.db"

    status = main(
        [
            "--host",
            "localhost",
            "--port",
            "8123",
            "--database-path",
            str(database_path),
            "--app-env",
            "test",
        ]
    )

    assert status == 0
    assert os.environ["DEPLOYMENT_MODE"] == "desktop"
    assert os.environ["APP_HOST"] == "localhost"
    assert os.environ["APP_PORT"] == "8123"
    assert os.environ["CORS_ORIGINS"] == ""
    assert os.environ["DATABASE_URL"] == _sqlite_url(database_path)
    assert os.environ["LIGHTHOUSE_CONFIG_FILE"] == str(
        database_path.with_name("backend.env").resolve()
    )
    assert captured == {
        "app_import": "app.main:app",
        "host": "localhost",
        "port": 8123,
        "log_level": "info",
        "access_log": False,
    }


def test_backup_utilities_create_and_validate_standalone_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_path = tmp_path / "source.db"
    backup_path = tmp_path / f"lighthouse.db.pre-{_current_head()}.bak"
    _create_source_database(source_path)

    create_status = main(
        [
            "--create-sqlite-backup",
            str(source_path),
            "--output-path",
            str(backup_path),
        ]
    )
    created = json.loads(capsys.readouterr().out)

    assert create_status == 0
    assert created["valid"] is True
    assert created["source_revision"] == SOURCE_REVISION
    assert backup_path.is_file()
    assert not backup_path.with_name(f"{backup_path.name}-wal").exists()

    validate_status = main(
        [
            "--validate-sqlite-backup",
            str(backup_path),
            "--migration-backup",
        ]
    )
    validated = json.loads(capsys.readouterr().out)

    assert validate_status == 0
    assert validated == {
        "integrity": "ok",
        "path": str(backup_path.resolve()),
        "revision_kind": "alembic",
        "source_revision": SOURCE_REVISION,
        "status": "VALID",
        "target_revision": _current_head(),
        "valid": True,
    }


def test_invalid_backup_utility_returns_structured_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backup_path = tmp_path / f"lighthouse.db.pre-{_current_head()}.bak"
    backup_path.write_bytes(b"invalid")

    status = main(
        [
            "--validate-sqlite-backup",
            str(backup_path),
            "--migration-backup",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert status == 2
    assert result["valid"] is False
    assert result["status"] == "INVALID"
    assert result["rule"] == "sqlite_integrity"
    assert result["path"] == str(backup_path.resolve())


def test_configuration_validation_utility_reports_valid_and_invalid_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    valid_path = tmp_path / "valid.env"
    valid_path.write_text(
        "JIRA_BASE_URL=https://example.atlassian.net\n"
        "JIRA_DONE_STATUSES=Done\n"
        "JIRA_IN_PROGRESS_STATUSES=In Progress\n"
        "JIRA_HIGH_SEVERITY_VALUES=High\n"
        "JIRA_BUG_ISSUE_TYPES=Bug\n",
        encoding="utf-8",
    )
    invalid_path = tmp_path / "invalid.env"
    invalid_path.write_text("JIRA_BASE_URL=not-a-url\n", encoding="utf-8")

    assert main(["--validate-env-file", str(valid_path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True

    assert main(["--validate-env-file", str(invalid_path)]) == 2
    invalid_result = json.loads(capsys.readouterr().out)
    assert invalid_result["valid"] is False
    assert invalid_result["rule"] == "utility"
