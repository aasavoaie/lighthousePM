"""Shared access to the installed, single-head Alembic migration graph."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def build_alembic_config() -> Config:
    backend_directory = Path(__file__).resolve().parents[2]
    script_location = backend_directory / "alembic"
    if not script_location.is_dir():
        raise RuntimeError(f"Alembic migration scripts are unavailable at {script_location}")

    config = Config()
    config.set_main_option("script_location", str(script_location))
    return config


def installed_revision_chain() -> tuple[str, ...]:
    script = ScriptDirectory.from_config(build_alembic_config())
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {len(heads)}")
    return tuple(revision.revision for revision in reversed(list(script.walk_revisions())))
