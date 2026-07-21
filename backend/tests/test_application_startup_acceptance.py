from collections.abc import Iterator
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, URL, make_url

from app.config import Settings
from app.db.session import create_database_engine


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
DESKTOP_ENTRY = BACKEND_DIRECTORY / "desktop_entry.py"
API_TOKEN = "phase-3-4-startup-acceptance-token"
REPRESENTATIVE_PRIOR_REVISION = "20260716_0010"
POSTGRES_ADMIN_URL_ENV = "MIGRATION_TEST_POSTGRES_ADMIN_URL"


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIRECTORY / "alembic"))
    return config


CURRENT_HEAD = ScriptDirectory.from_config(_alembic_config()).get_current_head()


def _sqlite_url(database_path: Path) -> str:
    return URL.create(
        drivername="sqlite+pysqlite",
        database=str(database_path),
    ).render_as_string(hide_password=False)


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request_json(
    origin_port: int,
    path: str,
    *,
    authenticated: bool = True,
) -> tuple[int, dict[str, object]]:
    headers = {"Authorization": f"Bearer {API_TOKEN}"} if authenticated else {}
    connection = http.client.HTTPConnection("127.0.0.1", origin_port, timeout=2)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)
    finally:
        connection.close()


def _wait_for_health(process: subprocess.Popen[bytes], port: int, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"backend exited with code {process.returncode}")
        try:
            status, payload = _request_json(port, "/health", authenticated=False)
            if status == 200 and payload.get("status") == "ok":
                return
        except (ConnectionError, OSError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(0.1)
    raise TimeoutError("backend did not report healthy before the startup deadline")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@contextmanager
def _running_backend_process(
    command_line: list[str],
    environment: dict[str, str],
    port: int,
    log_path: Path,
) -> Iterator[int]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            command_line,
            cwd=BACKEND_DIRECTORY,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    try:
        _wait_for_health(process, port)
        yield port
    except Exception as exc:
        _stop_process(process)
        output = log_path.read_text(encoding="utf-8", errors="replace")
        raise AssertionError(f"Backend startup acceptance failed: {exc}\n{output}") from exc
    finally:
        _stop_process(process)


@contextmanager
def _running_desktop_backend(database_path: Path, log_path: Path) -> Iterator[int]:
    port = _available_port()
    environment = {
        **os.environ,
        "JIRA_SYNC_ENABLED": "false",
        "JIRA_SYNC_INTERVAL_SECONDS": "0",
        "LIGHTHOUSE_API_TOKEN": API_TOKEN,
    }
    command_line = [
        sys.executable,
        str(DESKTOP_ENTRY),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--database-path",
        str(database_path),
        "--app-env",
        "test",
        "--log-level",
        "warning",
    ]
    with _running_backend_process(command_line, environment, port, log_path) as running_port:
        yield running_port


@contextmanager
def _running_postgres_backend(database_url: str, log_path: Path) -> Iterator[int]:
    port = _available_port()
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "APP_PORT": str(port),
        "CORS_ORIGINS": "",
        "DATABASE_URL": database_url,
        "JIRA_SYNC_ENABLED": "false",
        "JIRA_SYNC_INTERVAL_SECONDS": "0",
        "LIGHTHOUSE_API_TOKEN": API_TOKEN,
        "LOG_LEVEL": "WARNING",
    }
    command_line = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
        "--no-access-log",
    ]
    with _running_backend_process(command_line, environment, port, log_path) as running_port:
        yield running_port


def _seed_representative_records(connection) -> None:
    connection.execute(
        text(
            "INSERT INTO releases (release_id, name, project_key, status) "
            "VALUES ('MIG-REL', 'Preserved release', 'MIG', 'unreleased')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO sprints (sprint_id, name, state, project_key) "
            "VALUES ('MIG-SPRINT', 'Preserved sprint', 'active', 'MIG')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO issues "
            "(issue_key, summary, issue_type, status, priority, release_id, is_blocker, "
            "jira_changelog_complete) "
            "VALUES ('MIG-1', 'Preserved issue', 'Bug', 'Open', 'High', 'MIG-REL', false, false)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO issue_sprints (issue_key, sprint_id) "
            "VALUES ('MIG-1', 'MIG-SPRINT')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO metric_snapshots "
            "(release_id, snapshot_at, open_blockers, open_high_severity_bugs, "
            "scope_completed_pct, scope_churn_7d_pct, scope_added_7d_count, "
            "scope_removed_7d_count, median_cycle_time_days, reopen_rate_pct) "
            "VALUES ('MIG-REL', CURRENT_TIMESTAMP, 0, 1, 25, 5, 0, 0, 2, 10)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO sprint_metric_snapshots "
            "(sprint_id, snapshot_at, committed_scope, completed_scope_pct, open_blockers, "
            "open_high_severity_bugs, in_progress_count, not_started_count, rollover_count, "
            "median_cycle_time_days, reopen_rate_pct, story_point_total_count, "
            "story_point_pointed_count, story_point_unpointed_count, story_point_coverage_pct, "
            "story_point_unpointed_issue_keys, delivery_confidence_status, "
            "delivery_confidence_explanations, bugs_created_during_sprint_status, "
            "bugs_created_during_sprint_missing_created_at_issue_keys) "
            "VALUES ('MIG-SPRINT', CURRENT_TIMESTAMP, 1, 25, 0, 1, 1, 0, 0, 2, 10, "
            "1, 1, 0, 100, '[]', 'COMPUTED', '[]', 'COMPUTED', '[]')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO release_signals "
            "(release_id, metric_snapshot_id, ruleset_version, signal, reasons) "
            "SELECT 'MIG-REL', id, 0, 'YELLOW', '[\"Preserved signal\"]' "
            "FROM metric_snapshots WHERE release_id = 'MIG-REL'"
        )
    )


def _prepare_existing_database(
    database_engine: Engine,
    source_revision: str,
    *,
    unversioned: bool = False,
) -> None:
    config = _alembic_config()
    with database_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, source_revision)
        _seed_representative_records(connection)
        if unversioned:
            connection.execute(text("DROP TABLE alembic_version"))


def _assert_empty_api(port: int) -> None:
    release_status, releases = _request_json(port, "/releases")
    sprint_status, sprints = _request_json(port, "/sprints")

    assert release_status == 200
    assert releases["items"] == []
    assert releases["total"] == 0
    assert sprint_status == 200
    assert sprints["items"] == []
    assert sprints["total"] == 0


def _assert_representative_api(port: int) -> None:
    requests = {
        "/releases?project_key=MIG": "MIG-REL",
        "/sprints?project_key=MIG": "MIG-SPRINT",
        "/issues/MIG-1": "MIG-1",
        "/releases/MIG-REL/metrics": "MIG-REL",
        "/releases/MIG-REL/signal": "MIG-REL",
        "/sprints/MIG-SPRINT/metrics": "MIG-SPRINT",
    }

    for path, expected_identifier in requests.items():
        status, payload = _request_json(port, path)
        assert status == 200, (path, payload)
        if "items" in payload:
            assert payload["items"]
            item = payload["items"][0]
            assert expected_identifier in {item.get("release_id"), item.get("sprint_id")}
        else:
            assert expected_identifier in {
                payload.get("release_id"),
                payload.get("sprint_id"),
                payload.get("issue_key"),
            }


def _assert_database_revision(database_engine: Engine) -> None:
    with database_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == CURRENT_HEAD


def _create_postgres_test_database(admin_url: str) -> tuple[Engine, str]:
    parsed_admin_url = make_url(admin_url)
    if not parsed_admin_url.drivername.startswith("postgresql"):
        raise ValueError(f"{POSTGRES_ADMIN_URL_ENV} must use a PostgreSQL URL")

    database_name = f"lighthouse_startup_{os.getpid()}_{time.time_ns()}"
    admin_engine = create_engine(parsed_admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    return admin_engine, parsed_admin_url.set(database=database_name).render_as_string(
        hide_password=False
    )


def _drop_postgres_test_database(admin_engine: Engine, database_url: str) -> None:
    database_name = make_url(database_url).database
    if database_name is None or not database_name.startswith("lighthouse_startup_"):
        raise RuntimeError("Refusing to drop a database outside the startup-test namespace")

    with admin_engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        connection.execute(text(f'DROP DATABASE "{database_name}"'))
    admin_engine.dispose()


def test_clean_desktop_startup_creates_current_database_and_empty_api(tmp_path: Path) -> None:
    database_path = tmp_path / "new-user-data" / "lighthouse.db"
    backup_path = database_path.with_name(f"{database_path.name}.pre-{CURRENT_HEAD}.bak")
    assert not database_path.parent.exists()

    with _running_desktop_backend(database_path, tmp_path / "clean-start.log") as port:
        _assert_empty_api(port)

    assert database_path.is_file()
    assert not backup_path.exists()
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    try:
        _assert_database_revision(database_engine)
    finally:
        database_engine.dispose()


def test_existing_current_desktop_database_preserves_related_api_data(tmp_path: Path) -> None:
    database_path = tmp_path / "current" / "lighthouse.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    try:
        _prepare_existing_database(database_engine, CURRENT_HEAD)
    finally:
        database_engine.dispose()

    backup_path = database_path.with_name(f"{database_path.name}.pre-{CURRENT_HEAD}.bak")
    with _running_desktop_backend(database_path, tmp_path / "current-first.log") as port:
        _assert_representative_api(port)
    with _running_desktop_backend(database_path, tmp_path / "current-second.log") as port:
        _assert_representative_api(port)

    assert not backup_path.exists()


@pytest.mark.parametrize("unversioned", (False, True), ids=("versioned", "unversioned"))
def test_existing_older_desktop_database_migrates_before_api_readiness(
    tmp_path: Path,
    unversioned: bool,
) -> None:
    database_path = tmp_path / f"older-{'unversioned' if unversioned else 'versioned'}" / "lighthouse.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    try:
        _prepare_existing_database(
            database_engine,
            REPRESENTATIVE_PRIOR_REVISION,
            unversioned=unversioned,
        )
    finally:
        database_engine.dispose()

    backup_path = database_path.with_name(f"{database_path.name}.pre-{CURRENT_HEAD}.bak")
    with _running_desktop_backend(database_path, tmp_path / f"older-{unversioned}-first.log") as port:
        _assert_representative_api(port)

    assert backup_path.is_file()
    backup_mtime = backup_path.stat().st_mtime_ns
    with _running_desktop_backend(database_path, tmp_path / f"older-{unversioned}-second.log") as port:
        _assert_representative_api(port)

    assert backup_path.stat().st_mtime_ns == backup_mtime
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    try:
        _assert_database_revision(database_engine)
        assert "operational_status" in inspect(database_engine).get_table_names()
    finally:
        database_engine.dispose()


@pytest.mark.postgres
def test_clean_postgres_application_startup_creates_current_database_and_empty_api(
    tmp_path: Path,
) -> None:
    admin_url = os.getenv(POSTGRES_ADMIN_URL_ENV)
    if not admin_url:
        pytest.skip(f"Set {POSTGRES_ADMIN_URL_ENV} to run PostgreSQL startup acceptance")

    admin_engine, database_url = _create_postgres_test_database(admin_url)
    try:
        database_engine = create_database_engine(
            Settings(_env_file=None, database_url=database_url)
        )
        database_engine.dispose()
        with _running_postgres_backend(database_url, tmp_path / "postgres-clean.log") as port:
            _assert_empty_api(port)

        database_engine = create_database_engine(
            Settings(_env_file=None, database_url=database_url)
        )
        try:
            _assert_database_revision(database_engine)
        finally:
            database_engine.dispose()
    finally:
        _drop_postgres_test_database(admin_engine, database_url)


@pytest.mark.postgres
def test_existing_postgres_application_migrates_before_api_readiness(tmp_path: Path) -> None:
    admin_url = os.getenv(POSTGRES_ADMIN_URL_ENV)
    if not admin_url:
        pytest.skip(f"Set {POSTGRES_ADMIN_URL_ENV} to run PostgreSQL startup acceptance")

    admin_engine, database_url = _create_postgres_test_database(admin_url)
    try:
        database_engine = create_database_engine(
            Settings(_env_file=None, database_url=database_url)
        )
        try:
            _prepare_existing_database(database_engine, REPRESENTATIVE_PRIOR_REVISION)
        finally:
            database_engine.dispose()

        with _running_postgres_backend(database_url, tmp_path / "postgres-existing-first.log") as port:
            _assert_representative_api(port)
        with _running_postgres_backend(database_url, tmp_path / "postgres-existing-second.log") as port:
            _assert_representative_api(port)

        database_engine = create_database_engine(
            Settings(_env_file=None, database_url=database_url)
        )
        try:
            _assert_database_revision(database_engine)
        finally:
            database_engine.dispose()
    finally:
        _drop_postgres_test_database(admin_engine, database_url)
