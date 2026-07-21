from hashlib import sha256
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL

from app.config import Settings
from app.db.backup_validation import BackupValidationError, validate_sqlite_backup
from app.db.schema_revision import SchemaRevisionIdentity
from app.db.session import create_database_engine


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "20260407_0001"


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIRECTORY / "alembic"))
    return config


def _revision_chain() -> tuple[str, ...]:
    revisions = reversed(list(ScriptDirectory.from_config(_alembic_config()).walk_revisions()))
    return tuple(revision.revision for revision in revisions)


def _sqlite_url(database_path: Path) -> str:
    return URL.create(
        drivername="sqlite+pysqlite",
        database=str(database_path),
    ).render_as_string(hide_password=False)


def _create_backup_schema(
    backup_path: Path,
    *,
    revision: str = SOURCE_REVISION,
    remove_version: bool = False,
) -> None:
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(backup_path))
    )
    config = _alembic_config()
    try:
        with database_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
            connection.execute(
                text(
                    "INSERT INTO releases "
                    "(release_id, name, project_key, status) "
                    "VALUES ('validation-sentinel', 'Validation sentinel', 'VAL', 'unreleased')"
                )
            )
            if remove_version:
                connection.execute(text("DROP TABLE alembic_version"))
    finally:
        database_engine.dispose()


def _canonical_backup_path(tmp_path: Path) -> Path:
    return tmp_path / f"lighthouse.db.pre-{_revision_chain()[-1]}.bak"


def test_valid_versioned_backup_is_identified_without_modification(tmp_path: Path) -> None:
    backup_path = _canonical_backup_path(tmp_path)
    _create_backup_schema(backup_path)
    original_digest = sha256(backup_path.read_bytes()).digest()
    expected_source = SchemaRevisionIdentity(SOURCE_REVISION, "alembic")

    result = validate_sqlite_backup(
        backup_path,
        _revision_chain(),
        expected_source=expected_source,
        target_revision=_revision_chain()[-1],
        require_target_in_filename=True,
    )

    assert result.valid is True
    assert result.status == "VALID"
    assert result.integrity == "ok"
    assert result.source_revision == SOURCE_REVISION
    assert result.revision_kind == "alembic"
    assert result.target_revision == _revision_chain()[-1]
    assert sha256(backup_path.read_bytes()).digest() == original_digest


def test_recognized_unversioned_legacy_backup_is_valid(tmp_path: Path) -> None:
    backup_path = _canonical_backup_path(tmp_path)
    _create_backup_schema(backup_path, remove_version=True)

    result = validate_sqlite_backup(
        backup_path,
        _revision_chain(),
        expected_source=SchemaRevisionIdentity(SOURCE_REVISION, "recognized_legacy"),
        target_revision=_revision_chain()[-1],
        require_target_in_filename=True,
    )

    assert result.source_revision == SOURCE_REVISION
    assert result.revision_kind == "recognized_legacy"


@pytest.mark.parametrize(
    ("contents", "rule"),
    [
        (b"not sqlite", "sqlite_integrity"),
        (b"SQLite format 3\x00", "sqlite_integrity"),
    ],
)
def test_corrupt_or_truncated_backup_is_rejected(
    tmp_path: Path,
    contents: bytes,
    rule: str,
) -> None:
    backup_path = _canonical_backup_path(tmp_path)
    backup_path.write_bytes(contents)

    with pytest.raises(BackupValidationError) as raised:
        validate_sqlite_backup(backup_path, _revision_chain())

    assert raised.value.rule == rule
    assert str(backup_path.resolve()) in str(raised.value)


def test_missing_and_symbolic_link_backups_are_rejected(tmp_path: Path) -> None:
    missing_path = _canonical_backup_path(tmp_path)
    with pytest.raises(BackupValidationError) as missing:
        validate_sqlite_backup(missing_path, _revision_chain())
    assert missing.value.rule == "file_type"

    real_path = tmp_path / "real.db"
    _create_backup_schema(real_path)
    linked_path = _canonical_backup_path(tmp_path)
    try:
        linked_path.symlink_to(real_path)
    except OSError as exc:
        pytest.skip(f"Symbolic links are unavailable: {exc}")

    with pytest.raises(BackupValidationError) as linked:
        validate_sqlite_backup(linked_path, _revision_chain())
    assert linked.value.rule == "file_type"


@pytest.mark.parametrize("state", ["empty", "multiple", "unknown"])
def test_invalid_alembic_revision_states_are_rejected(tmp_path: Path, state: str) -> None:
    backup_path = _canonical_backup_path(tmp_path)
    _create_backup_schema(backup_path)
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(backup_path))
    )
    try:
        with database_engine.begin() as connection:
            if state == "empty":
                connection.execute(text("DELETE FROM alembic_version"))
            elif state == "multiple":
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES ('20260424_0002')")
                )
            else:
                connection.execute(
                    text("UPDATE alembic_version SET version_num = 'future_or_unknown'")
                )
    finally:
        database_engine.dispose()

    with pytest.raises(BackupValidationError) as raised:
        validate_sqlite_backup(backup_path, _revision_chain())
    assert raised.value.rule == "schema_revision"


def test_source_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    backup_path = _canonical_backup_path(tmp_path)
    _create_backup_schema(backup_path)

    with pytest.raises(BackupValidationError) as raised:
        validate_sqlite_backup(
            backup_path,
            _revision_chain(),
            expected_source=SchemaRevisionIdentity("20260424_0002", "alembic"),
        )
    assert raised.value.rule == "source_revision"


def test_invalid_target_and_filename_relationships_are_rejected(tmp_path: Path) -> None:
    wrong_name_path = tmp_path / "lighthouse.db.pre-wrong.bak"
    _create_backup_schema(wrong_name_path)

    with pytest.raises(BackupValidationError) as filename_error:
        validate_sqlite_backup(
            wrong_name_path,
            _revision_chain(),
            target_revision=_revision_chain()[-1],
            require_target_in_filename=True,
        )
    assert filename_error.value.rule == "filename_target"

    with pytest.raises(BackupValidationError) as relationship_error:
        validate_sqlite_backup(
            wrong_name_path,
            _revision_chain(),
            target_revision=SOURCE_REVISION,
        )
    assert relationship_error.value.rule == "revision_relationship"
