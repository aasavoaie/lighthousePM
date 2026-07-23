from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine, URL

from app.config import Settings
from app.db.base import Base
from app.db.migrations import LEGACY_REVISION_SHAPES, migrate_database
from app.db.session import create_database_engine
from tests.postgres_test_support import (
    create_postgres_test_database,
    drop_postgres_test_database,
    postgres_admin_url_or_skip,
)


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIRECTORY / "alembic"))
    return config


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(_alembic_config())


MIGRATION_REVISIONS = tuple(
    revision.revision for revision in reversed(list(_script_directory().walk_revisions()))
)
CURRENT_HEAD = MIGRATION_REVISIONS[-1]
PRIOR_VERSIONED_REVISIONS = MIGRATION_REVISIONS[:-1]
LEGACY_REVISIONS = tuple(shape.revision for shape in LEGACY_REVISION_SHAPES)


def _sqlite_url(database_path: Path) -> str:
    return URL.create(
        drivername="sqlite+pysqlite",
        database=str(database_path),
    ).render_as_string(hide_password=False)


def _upgrade_to_source_and_seed(
    database_engine: Engine,
    source_revision: str,
    sentinel_id: str,
    *,
    remove_version_tracking: bool = False,
) -> None:
    config = _alembic_config()
    with database_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, source_revision)
        connection.execute(
            text(
                "INSERT INTO releases (release_id, name, project_key, status) "
                "VALUES (:release_id, 'Migration sentinel', 'MIG', 'unreleased')"
            ),
            {"release_id": sentinel_id},
        )
        if remove_version_tracking:
            connection.execute(text("DROP TABLE alembic_version"))


def _assert_current_database(database_engine: Engine, sentinel_id: str) -> None:
    schema = inspect(database_engine)
    actual_tables = set(schema.get_table_names())

    for table_name, table in Base.metadata.tables.items():
        assert table_name in actual_tables
        actual_columns = {column["name"] for column in schema.get_columns(table_name)}
        assert set(table.columns.keys()).issubset(actual_columns)

    with database_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == CURRENT_HEAD
        assert connection.scalar(
            text("SELECT name FROM releases WHERE release_id = :release_id"),
            {"release_id": sentinel_id},
        ) == "Migration sentinel"


def _assert_second_start_is_idempotent(database_engine: Engine) -> None:
    migrate_database(database_engine)
    with database_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == CURRENT_HEAD


@pytest.mark.parametrize("source_revision", PRIOR_VERSIONED_REVISIONS, ids=PRIOR_VERSIONED_REVISIONS)
def test_every_versioned_sqlite_revision_upgrades_to_head(
    tmp_path: Path,
    source_revision: str,
) -> None:
    database_path = tmp_path / f"versioned-{source_revision}.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    sentinel_id = f"versioned-{source_revision}"

    try:
        _upgrade_to_source_and_seed(database_engine, source_revision, sentinel_id)
        migrate_database(database_engine)
        _assert_current_database(database_engine, sentinel_id)

        backup_path = database_path.with_name(f"{database_path.name}.pre-{CURRENT_HEAD}.bak")
        assert backup_path.is_file()
        backup_mtime = backup_path.stat().st_mtime_ns

        _assert_second_start_is_idempotent(database_engine)
        assert backup_path.stat().st_mtime_ns == backup_mtime
    finally:
        database_engine.dispose()


@pytest.mark.parametrize("source_revision", LEGACY_REVISIONS, ids=LEGACY_REVISIONS)
def test_every_registered_unversioned_sqlite_revision_upgrades_to_head(
    tmp_path: Path,
    source_revision: str,
) -> None:
    database_path = tmp_path / f"unversioned-{source_revision}.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    sentinel_id = f"unversioned-{source_revision}"

    try:
        _upgrade_to_source_and_seed(
            database_engine,
            source_revision,
            sentinel_id,
            remove_version_tracking=True,
        )
        migrate_database(database_engine)
        _assert_current_database(database_engine, sentinel_id)

        backup_path = database_path.with_name(f"{database_path.name}.pre-{CURRENT_HEAD}.bak")
        assert backup_path.is_file()
        backup_mtime = backup_path.stat().st_mtime_ns

        _assert_second_start_is_idempotent(database_engine)
        assert backup_path.stat().st_mtime_ns == backup_mtime
    finally:
        database_engine.dispose()


def test_current_sqlite_head_is_idempotent_without_backup(tmp_path: Path) -> None:
    database_path = tmp_path / "current-head.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )

    try:
        _upgrade_to_source_and_seed(database_engine, CURRENT_HEAD, "current-head")
        _assert_second_start_is_idempotent(database_engine)
        _assert_current_database(database_engine, "current-head")
        assert not database_path.with_name(f"{database_path.name}.pre-{CURRENT_HEAD}.bak").exists()
    finally:
        database_engine.dispose()


def test_legacy_registry_is_an_ordered_prefix_of_the_migration_graph() -> None:
    assert LEGACY_REVISIONS == MIGRATION_REVISIONS[: len(LEGACY_REVISIONS)]


def test_unversioned_schema_newer_than_legacy_registry_is_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "newer-unversioned.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )

    try:
        _upgrade_to_source_and_seed(
            database_engine,
            "20260716_0011",
            "newer-unversioned",
            remove_version_tracking=True,
        )

        with pytest.raises(RuntimeError, match="newer than the supported legacy registry"):
            migrate_database(database_engine)

        with database_engine.connect() as connection:
            assert "alembic_version" not in inspect(connection).get_table_names()
            assert connection.scalar(
                text("SELECT name FROM releases WHERE release_id = 'newer-unversioned'")
            ) == "Migration sentinel"
    finally:
        database_engine.dispose()


def test_empty_alembic_version_state_is_rejected_without_data_changes(tmp_path: Path) -> None:
    database_path = tmp_path / "empty-version.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )

    try:
        _upgrade_to_source_and_seed(database_engine, "20260407_0001", "empty-version")
        with database_engine.begin() as connection:
            connection.execute(text("DELETE FROM alembic_version"))

        with pytest.raises(RuntimeError, match="without a recorded revision"):
            migrate_database(database_engine)

        with database_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT name FROM releases WHERE release_id = 'empty-version'")
            ) == "Migration sentinel"
    finally:
        database_engine.dispose()


def test_multiple_recorded_revisions_are_rejected_without_data_changes(tmp_path: Path) -> None:
    database_path = tmp_path / "multiple-versions.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )

    try:
        _upgrade_to_source_and_seed(database_engine, "20260407_0001", "multiple-versions")
        with database_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) "
                    "VALUES ('20260424_0002')"
                )
            )

        with pytest.raises(RuntimeError, match="multiple Alembic revisions"):
            migrate_database(database_engine)

        with database_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT name FROM releases WHERE release_id = 'multiple-versions'")
            ) == "Migration sentinel"
    finally:
        database_engine.dispose()


def test_unknown_recorded_revision_is_rejected_without_data_changes(tmp_path: Path) -> None:
    database_path = tmp_path / "unknown-version.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )

    try:
        _upgrade_to_source_and_seed(database_engine, "20260407_0001", "unknown-version")
        with database_engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = 'unknown_revision'")
            )

        with pytest.raises(RuntimeError, match="unknown Alembic revision"):
            migrate_database(database_engine)

        with database_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT name FROM releases WHERE release_id = 'unknown-version'")
            ) == "Migration sentinel"
    finally:
        database_engine.dispose()


@pytest.mark.postgres
@pytest.mark.parametrize("source_revision", MIGRATION_REVISIONS, ids=MIGRATION_REVISIONS)
def test_every_versioned_postgres_revision_upgrades_to_head(source_revision: str) -> None:
    admin_url = postgres_admin_url_or_skip()
    admin_engine, database_url = create_postgres_test_database(
        admin_url,
        prefix="lighthouse_migration_",
    )
    try:
        database_engine = create_database_engine(
            Settings(_env_file=None, database_url=database_url)
        )
        sentinel_id = f"versioned-{source_revision}"
        try:
            _upgrade_to_source_and_seed(database_engine, source_revision, sentinel_id)
            migrate_database(database_engine)
            _assert_current_database(database_engine, sentinel_id)
            _assert_second_start_is_idempotent(database_engine)
        finally:
            database_engine.dispose()
    finally:
        drop_postgres_test_database(admin_engine, database_url)
