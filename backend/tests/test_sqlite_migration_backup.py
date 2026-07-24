from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine, URL

import app.db.migrations as migration_module
from app.config import Settings
from app.db.backup_validation import BackupValidationError
from app.db.migrations import migrate_database
from app.db.session import create_database_engine


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "20260407_0001"


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIRECTORY / "alembic"))
    return config


def _current_head() -> str:
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
    assert len(heads) == 1
    return heads[0]


def _sqlite_url(database_path: Path) -> str:
    return URL.create(
        drivername="sqlite+pysqlite",
        database=str(database_path),
    ).render_as_string(hide_password=False)


def _prepare_source_database(database_path: Path) -> Engine:
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    config = _alembic_config()
    with database_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, SOURCE_REVISION)
        connection.execute(
            text(
                "INSERT INTO releases "
                "(release_id, name, project_key, status) "
                "VALUES ('backup-sentinel', 'Backup sentinel', 'BKP', 'unreleased')"
            )
        )
    return database_engine


def _backup_path(database_path: Path) -> Path:
    return database_path.with_name(f"{database_path.name}.pre-{_current_head()}.bak")


def _temporary_paths(backup_path: Path) -> list[Path]:
    return list(backup_path.parent.glob(f".{backup_path.name}.*.tmp"))


def _assert_source_unchanged(database_engine: Engine) -> None:
    with database_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == SOURCE_REVISION
        assert connection.scalar(
            text("SELECT name FROM releases WHERE release_id = 'backup-sentinel'")
        ) == "Backup sentinel"


def _assert_backup_contains_source_data(backup_path: Path) -> None:
    with sqlite3.connect(backup_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            SOURCE_REVISION,
        )
        assert connection.execute(
            "SELECT name FROM releases WHERE release_id = 'backup-sentinel'"
        ).fetchone() == ("Backup sentinel",)


def _copy_database(source_path: Path, target_path: Path) -> None:
    with closing(sqlite3.connect(source_path)) as source_connection:
        with closing(sqlite3.connect(target_path)) as target_connection:
            source_connection.backup(target_connection)


def test_sqlite_backup_is_atomically_published_without_temporary_files(tmp_path: Path) -> None:
    database_path = tmp_path / "successful.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)

    try:
        migrate_database(database_engine)

        assert backup_path.is_file()
        assert _temporary_paths(backup_path) == []
        _assert_backup_contains_source_data(backup_path)
    finally:
        database_engine.dispose()


def test_sqlite_backup_copy_failure_stops_migration_and_can_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "copy-failure.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)

    def fail_copy(_database_engine: Engine, target_path: Path) -> None:
        target_path.write_bytes(b"partial backup")
        raise OSError("simulated backup copy failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(migration_module, "_copy_sqlite_database", fail_copy)
            with pytest.raises(OSError, match="simulated backup copy failure"):
                migrate_database(database_engine)

        assert not backup_path.exists()
        assert _temporary_paths(backup_path) == []
        _assert_source_unchanged(database_engine)

        migrate_database(database_engine)
        assert backup_path.is_file()
        assert _temporary_paths(backup_path) == []
        _assert_backup_contains_source_data(backup_path)
    finally:
        database_engine.dispose()


def test_sqlite_backup_publication_failure_stops_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "publication-failure.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)

    def fail_publication(_source: Path, _target: Path) -> None:
        raise PermissionError("simulated backup publication failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(migration_module.os, "link", fail_publication)
            with pytest.raises(PermissionError, match="simulated backup publication failure"):
                migrate_database(database_engine)

        assert not backup_path.exists()
        assert _temporary_paths(backup_path) == []
        _assert_source_unchanged(database_engine)
    finally:
        database_engine.dispose()


def test_sqlite_backup_flush_failure_stops_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "flush-failure.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)

    def fail_flush(_target_path: Path) -> None:
        raise OSError("simulated backup flush failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(migration_module, "_flush_file", fail_flush)
            with pytest.raises(OSError, match="simulated backup flush failure"):
                migrate_database(database_engine)

        assert not backup_path.exists()
        assert _temporary_paths(backup_path) == []
        _assert_source_unchanged(database_engine)
    finally:
        database_engine.dispose()


def test_new_backup_validation_failure_stops_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "validation-failure.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)

    def fail_validation(path: Path, *_args, **_kwargs) -> None:
        assert not backup_path.exists()
        raise BackupValidationError(path, "sqlite_integrity", "simulated validation failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(migration_module, "validate_sqlite_backup", fail_validation)
            with pytest.raises(BackupValidationError, match="simulated validation failure"):
                migrate_database(database_engine)

        assert not backup_path.exists()
        assert _temporary_paths(backup_path) == []
        _assert_source_unchanged(database_engine)
    finally:
        database_engine.dispose()


def test_invalid_existing_canonical_backup_stops_before_migration(tmp_path: Path) -> None:
    database_path = tmp_path / "invalid-existing.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)
    invalid_contents = b"invalid canonical backup"
    backup_path.write_bytes(invalid_contents)

    try:
        with pytest.raises(BackupValidationError) as raised:
            migrate_database(database_engine)

        assert raised.value.path == backup_path.resolve()
        assert raised.value.rule == "sqlite_integrity"
        assert backup_path.read_bytes() == invalid_contents
        _assert_source_unchanged(database_engine)
    finally:
        database_engine.dispose()


def test_stale_temporary_backup_is_ignored_during_retry(tmp_path: Path) -> None:
    database_path = tmp_path / "stale-temporary.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)
    stale_path = backup_path.with_name(f".{backup_path.name}.stale.tmp")
    stale_path.write_bytes(b"not a database")

    try:
        migrate_database(database_engine)

        assert stale_path.read_bytes() == b"not a database"
        assert backup_path.read_bytes().startswith(b"SQLite format 3\x00")
        _assert_backup_contains_source_data(backup_path)
    finally:
        database_engine.dispose()


def test_concurrently_published_canonical_backup_is_not_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "publication-race.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)
    copy_sqlite_database = migration_module._copy_sqlite_database
    competing_digest: bytes | None = None

    def publish_competing_backup(source_engine: Engine, target_path: Path) -> None:
        nonlocal competing_digest
        copy_sqlite_database(source_engine, target_path)
        migration_module.os.link(target_path, backup_path)
        competing_digest = sha256(backup_path.read_bytes()).digest()

    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                migration_module,
                "_copy_sqlite_database",
                publish_competing_backup,
            )
            migrate_database(database_engine)

        assert competing_digest is not None
        assert sha256(backup_path.read_bytes()).digest() == competing_digest
        assert _temporary_paths(backup_path) == []
        _assert_backup_contains_source_data(backup_path)
    finally:
        database_engine.dispose()


def test_existing_canonical_backup_is_not_overwritten(tmp_path: Path) -> None:
    database_path = tmp_path / "existing-backup.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)
    _copy_database(database_path, backup_path)
    original_digest = sha256(backup_path.read_bytes()).digest()
    original_modified_at = backup_path.stat().st_mtime_ns

    try:
        migrate_database(database_engine)

        assert sha256(backup_path.read_bytes()).digest() == original_digest
        assert backup_path.stat().st_mtime_ns == original_modified_at
        _assert_backup_contains_source_data(backup_path)
    finally:
        database_engine.dispose()


def test_sqlite_backup_includes_committed_wal_data(tmp_path: Path) -> None:
    database_path = tmp_path / "wal-data.db"
    database_engine = _prepare_source_database(database_path)
    backup_path = _backup_path(database_path)

    try:
        with database_engine.begin() as connection:
            connection.execute(text("PRAGMA wal_autocheckpoint = 0"))
            connection.execute(
                text(
                    "INSERT INTO releases "
                    "(release_id, name, project_key, status) "
                    "VALUES ('wal-sentinel', 'WAL sentinel', 'BKP', 'unreleased')"
                )
            )

        wal_path = database_path.with_name(f"{database_path.name}-wal")
        assert wal_path.is_file()
        assert wal_path.stat().st_size > 0

        migrate_database(database_engine)

        with sqlite3.connect(backup_path) as connection:
            assert connection.execute(
                "SELECT name FROM releases WHERE release_id = 'wal-sentinel'"
            ).fetchone() == ("WAL sentinel",)
    finally:
        database_engine.dispose()
