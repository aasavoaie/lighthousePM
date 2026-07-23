"""Read-only validation for SQLite backups used by migration and desktop recovery."""

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Literal

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import StaticPool

from app.db.schema_revision import SchemaRevisionIdentity, identify_schema_revision


MIGRATION_BACKUP_PATTERN = re.compile(r"\.pre-(?P<target>[^.]+)\.bak$")


@dataclass(frozen=True)
class SQLiteBackupValidation:
    path: str
    integrity: Literal["ok"]
    source_revision: str
    revision_kind: Literal["alembic", "recognized_legacy"]
    target_revision: str | None
    valid: Literal[True] = True
    status: Literal["VALID"] = "VALID"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class BackupValidationError(RuntimeError):
    def __init__(self, path: Path, rule: str, detail: str) -> None:
        self.path = path
        self.rule = rule
        self.detail = detail
        super().__init__(f"Backup validation failed for {path}: {rule}: {detail}")

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": False,
            "status": "INVALID",
            "path": str(self.path),
            "rule": self.rule,
            "detail": self.detail,
        }


def validate_sqlite_backup(
    backup_path: Path,
    revision_chain: tuple[str, ...],
    *,
    expected_source: SchemaRevisionIdentity | None = None,
    target_revision: str | None = None,
    require_target_in_filename: bool = False,
) -> SQLiteBackupValidation:
    candidate_path = backup_path.expanduser().absolute()
    _validate_regular_file(candidate_path)
    path = candidate_path.resolve()
    known_revisions = set(revision_chain)

    database_engine = _create_read_only_sqlite_engine(path)
    try:
        try:
            with database_engine.connect() as connection:
                _validate_integrity(connection, path)
                identity = _identify_revision(connection, known_revisions, path)
        except BackupValidationError:
            raise
        except Exception as exc:
            raise BackupValidationError(path, "sqlite_open", str(exc)) from exc
    finally:
        database_engine.dispose()

    if expected_source is not None and identity != expected_source:
        raise BackupValidationError(
            path,
            "source_revision",
            "backup source "
            f"{identity.kind}:{identity.revision} does not match active source "
            f"{expected_source.kind}:{expected_source.revision}",
        )

    if target_revision is not None:
        _validate_revision_relationship(
            path, identity.revision, target_revision, revision_chain
        )
    if require_target_in_filename:
        _validate_filename_target(path, target_revision)

    return SQLiteBackupValidation(
        path=str(path),
        integrity="ok",
        source_revision=identity.revision,
        revision_kind=identity.kind,
        target_revision=target_revision,
    )


def migration_target_from_filename(backup_path: Path) -> str:
    path = backup_path.expanduser().resolve()
    match = MIGRATION_BACKUP_PATTERN.search(path.name)
    if match is None:
        raise BackupValidationError(
            path,
            "filename_target",
            "filename must end with .pre-<target-revision>.bak",
        )
    return match.group("target")


def create_standalone_sqlite_backup(
    source_path: Path,
    target_path: Path,
    revision_chain: tuple[str, ...],
) -> SQLiteBackupValidation:
    source_candidate = source_path.expanduser().absolute()
    source_validation = validate_sqlite_backup(source_candidate, revision_chain)
    source = Path(source_validation.path)
    source_identity = SchemaRevisionIdentity(
        source_validation.source_revision,
        source_validation.revision_kind,
    )

    target_candidate = target_path.expanduser().absolute()
    if target_candidate.is_symlink():
        raise BackupValidationError(
            target_candidate,
            "file_type",
            "standalone backup target must not be a symbolic link",
        )
    target = target_candidate.resolve()
    if target.exists():
        raise BackupValidationError(
            target,
            "target_exists",
            "standalone backup target already exists",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.close(temporary_descriptor)
        _copy_sqlite_file(source, temporary_path)
        _flush_file(temporary_path)
        validation = validate_sqlite_backup(
            temporary_path,
            revision_chain,
            expected_source=source_identity,
        )
        try:
            os.rename(temporary_path, target)
        except FileExistsError as exc:
            raise BackupValidationError(
                target,
                "target_exists",
                "standalone backup target already exists",
            ) from exc
        return SQLiteBackupValidation(
            path=str(target),
            integrity=validation.integrity,
            source_revision=validation.source_revision,
            revision_kind=validation.revision_kind,
            target_revision=None,
        )
    finally:
        _remove_temporary_file(temporary_path)


def _validate_regular_file(path: Path) -> None:
    if path.is_symlink():
        raise BackupValidationError(
            path, "file_type", "backup must not be a symbolic link"
        )
    if not path.is_file():
        raise BackupValidationError(
            path, "file_type", "backup must be a readable regular file"
        )


def _create_read_only_sqlite_engine(path: Path) -> Engine:
    database_uri = f"{path.as_uri()}?mode=ro"

    def connect_read_only() -> sqlite3.Connection:
        return sqlite3.connect(database_uri, uri=True)

    return create_engine(
        "sqlite+pysqlite://",
        creator=connect_read_only,
        poolclass=StaticPool,
    )


def _copy_sqlite_file(source_path: Path, target_path: Path) -> None:
    source_connection: sqlite3.Connection | None = None
    target_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True)
        target_connection = sqlite3.connect(target_path)
        source_connection.backup(target_connection)
    finally:
        try:
            if target_connection is not None:
                target_connection.close()
        finally:
            if source_connection is not None:
                source_connection.close()


def _flush_file(path: Path) -> None:
    with path.open("r+b") as backup_file:
        backup_file.flush()
        os.fsync(backup_file.fileno())


def _remove_temporary_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _validate_integrity(connection: Connection, path: Path) -> None:
    try:
        results = list(connection.exec_driver_sql("PRAGMA integrity_check").scalars())
    except Exception as exc:
        raise BackupValidationError(path, "sqlite_integrity", str(exc)) from exc
    if results != ["ok"]:
        detail = (
            "; ".join(str(result) for result in results)
            or "integrity check returned no result"
        )
        raise BackupValidationError(path, "sqlite_integrity", detail)


def _identify_revision(
    connection: Connection,
    known_revisions: set[str],
    path: Path,
) -> SchemaRevisionIdentity:
    try:
        return identify_schema_revision(connection, known_revisions)
    except Exception as exc:
        raise BackupValidationError(path, "schema_revision", str(exc)) from exc


def _validate_revision_relationship(
    path: Path,
    source_revision: str,
    target_revision: str,
    revision_chain: tuple[str, ...],
) -> None:
    if target_revision not in revision_chain:
        raise BackupValidationError(
            path,
            "target_revision",
            f"target revision {target_revision!r} is not in the installed migration chain",
        )
    if source_revision not in revision_chain:
        raise BackupValidationError(
            path,
            "source_revision",
            f"source revision {source_revision!r} is not in the installed migration chain",
        )
    if revision_chain.index(source_revision) >= revision_chain.index(target_revision):
        raise BackupValidationError(
            path,
            "revision_relationship",
            f"source revision {source_revision!r} is not an ancestor of target {target_revision!r}",
        )


def _validate_filename_target(path: Path, target_revision: str | None) -> None:
    if target_revision is None:
        raise BackupValidationError(
            path, "filename_target", "expected target revision is unavailable"
        )
    expected_suffix = f".pre-{target_revision}.bak"
    if not path.name.endswith(expected_suffix):
        raise BackupValidationError(
            path,
            "filename_target",
            f"filename must end with {expected_suffix!r}",
        )
