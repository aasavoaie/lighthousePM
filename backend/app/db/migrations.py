"""Deterministic database migration orchestration for application startup."""

import os
from pathlib import Path
import sqlite3
import tempfile

from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.db.backup_validation import validate_sqlite_backup
from app.db.migration_graph import build_alembic_config
from app.db.schema_revision import LEGACY_REVISION_SHAPES as LEGACY_REVISION_SHAPES
from app.db.schema_revision import SchemaRevisionIdentity, infer_legacy_revision


def migrate_database(database_engine: Engine) -> None:
    """Upgrade a fresh, versioned, or recognized legacy database to Alembic head."""
    alembic_config = build_alembic_config()
    script = ScriptDirectory.from_config(alembic_config)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {len(heads)}")
    target_revision = heads[0]
    revision_chain = tuple(
        revision.revision for revision in reversed(list(script.walk_revisions()))
    )

    with database_engine.begin() as connection:
        current_revisions = MigrationContext.configure(connection).get_current_heads()
        table_names = set(inspect(connection).get_table_names())
        has_application_schema = bool(table_names - {"alembic_version"})

        if len(current_revisions) > 1:
            raise RuntimeError(
                "Database records multiple Alembic revisions; automatic migration was stopped"
            )
        current_revision = current_revisions[0] if current_revisions else None

        if "alembic_version" in table_names and current_revision is None:
            raise RuntimeError(
                "Alembic version table exists without a recorded revision; automatic migration was stopped"
            )

        known_revisions = {revision.revision for revision in script.walk_revisions()}
        if current_revision is not None and current_revision not in known_revisions:
            raise RuntimeError(
                f"Database records unknown Alembic revision {current_revision!r}; "
                "automatic migration was stopped"
            )

        if current_revision == target_revision:
            return

        source_identity: SchemaRevisionIdentity | None = None
        if current_revision is not None:
            source_identity = SchemaRevisionIdentity(current_revision, "alembic")
        elif has_application_schema:
            source_identity = SchemaRevisionIdentity(
                infer_legacy_revision(connection),
                "recognized_legacy",
            )

        if has_application_schema and database_engine.dialect.name == "sqlite":
            if source_identity is None:
                raise RuntimeError("Existing SQLite schema revision could not be identified")
            _create_sqlite_backup(
                database_engine,
                target_revision,
                revision_chain,
                source_identity,
            )

        alembic_config.attributes["connection"] = connection
        if current_revision is None and source_identity is not None:
            command.stamp(alembic_config, source_identity.revision)

        command.upgrade(alembic_config, "head")


def _create_sqlite_backup(
    database_engine: Engine,
    target_revision: str,
    revision_chain: tuple[str, ...],
    source_identity: SchemaRevisionIdentity,
) -> Path | None:
    database_name = database_engine.url.database
    if not database_name or database_name == ":memory:" or database_name.startswith("file:"):
        return None

    database_path = Path(database_name).expanduser().resolve()
    backup_path = database_path.with_name(f"{database_path.name}.pre-{target_revision}.bak")
    if backup_path.exists():
        validate_sqlite_backup(
            backup_path,
            revision_chain,
            expected_source=source_identity,
            target_revision=target_revision,
            require_target_in_filename=True,
        )
        return backup_path

    temporary_descriptor, temporary_name = tempfile.mkstemp(
        dir=backup_path.parent,
        prefix=f".{backup_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)

    try:
        os.close(temporary_descriptor)
        _copy_sqlite_database(database_engine, temporary_path)
        _flush_file(temporary_path)
        validate_sqlite_backup(
            temporary_path,
            revision_chain,
            expected_source=source_identity,
            target_revision=target_revision,
        )
        try:
            os.link(temporary_path, backup_path)
        except FileExistsError:
            validate_sqlite_backup(
                backup_path,
                revision_chain,
                expected_source=source_identity,
                target_revision=target_revision,
                require_target_in_filename=True,
            )
    finally:
        _remove_temporary_backup(temporary_path)
    return backup_path


def _copy_sqlite_database(database_engine: Engine, target_path: Path) -> None:
    raw_connection = database_engine.raw_connection()
    target_connection: sqlite3.Connection | None = None
    try:
        source_connection = raw_connection.driver_connection
        if not isinstance(source_connection, sqlite3.Connection):
            raise RuntimeError("SQLite backup requires a sqlite3 driver connection")
        target_connection = sqlite3.connect(target_path)
        source_connection.backup(target_connection)
    finally:
        try:
            if target_connection is not None:
                target_connection.close()
        finally:
            raw_connection.close()


def _flush_file(path: Path) -> None:
    with path.open("r+b") as backup_file:
        backup_file.flush()
        os.fsync(backup_file.fileno())


def _remove_temporary_backup(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # A stale temporary file is non-authoritative and cannot be mistaken
        # for the canonical .bak path. A later startup creates a unique file.
        pass
