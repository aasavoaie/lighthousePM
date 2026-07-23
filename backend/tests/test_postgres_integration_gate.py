from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import run_postgres_integration as gate
from tests import postgres_test_support as support


ADMIN_URL = "postgresql+psycopg://postgres:synthetic@127.0.0.1:5432/postgres"


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class _FakeItem:
    def __init__(self, nodeid: str, *, postgres: bool) -> None:
        self.nodeid = nodeid
        self._postgres = postgres

    def get_closest_marker(self, marker_name: str):
        if marker_name == "postgres" and self._postgres:
            return object()
        return None


def test_disposable_database_names_are_explicit_and_bounded() -> None:
    assert support.is_disposable_database_name("lighthouse_migration_abc123")
    assert support.is_disposable_database_name("lighthouse_startup_abc123")
    assert not support.is_disposable_database_name("lighthouse")
    assert not support.is_disposable_database_name("lighthouse_migration_bad-name")
    assert not support.is_disposable_database_name("other_migration_abc123")


def test_admin_url_must_be_postgres_and_must_not_target_a_test_database() -> None:
    support.validate_postgres_admin_url(ADMIN_URL)
    with pytest.raises(ValueError, match="must use a PostgreSQL URL"):
        support.validate_postgres_admin_url("sqlite:///local.db")
    with pytest.raises(ValueError, match="must target the postgres administrative database"):
        support.validate_postgres_admin_url(
            "postgresql+psycopg://postgres@127.0.0.1/lighthouse"
        )
    with pytest.raises(ValueError, match="must not target a disposable test database"):
        support.validate_postgres_admin_url(
            "postgresql+psycopg://postgres@127.0.0.1/lighthouse_startup_abc123"
        )


def test_database_cleanup_refuses_non_test_names_and_disposes_engine() -> None:
    engine = _FakeEngine()
    with pytest.raises(RuntimeError, match="Refusing to drop"):
        support.drop_postgres_test_database(engine, ADMIN_URL)  # type: ignore[arg-type]
    assert engine.disposed is True


def test_missing_admin_url_skips_optional_runs_and_fails_required_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(support.POSTGRES_ADMIN_URL_ENV, raising=False)
    monkeypatch.delenv(support.REQUIRE_POSTGRES_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception):
        support.postgres_admin_url_or_skip()

    monkeypatch.setenv(support.REQUIRE_POSTGRES_ENV, "1")
    with pytest.raises(pytest.fail.Exception):
        support.postgres_admin_url_or_skip()


def test_gate_requires_explicit_mode_and_admin_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(support.REQUIRE_POSTGRES_ENV, raising=False)
    monkeypatch.delenv(support.POSTGRES_ADMIN_URL_ENV, raising=False)
    with pytest.raises(RuntimeError, match=support.REQUIRE_POSTGRES_ENV):
        gate._require_configuration(command_line_required=False)

    monkeypatch.setenv(support.REQUIRE_POSTGRES_ENV, "1")
    with pytest.raises(RuntimeError, match=support.POSTGRES_ADMIN_URL_ENV):
        gate._require_configuration(command_line_required=False)

    monkeypatch.setenv(support.POSTGRES_ADMIN_URL_ENV, ADMIN_URL)
    assert gate._require_configuration(command_line_required=False) == ADMIN_URL


def test_required_plugin_rejects_zero_collection_and_skips() -> None:
    plugin = gate.RequiredPostgresPlugin()
    assert plugin.completion_errors() == [
        "PostgreSQL integration collected no postgres-marked tests."
    ]

    plugin.pytest_collection_modifyitems(
        [
            _FakeItem("test_gate.py::test_postgres", postgres=True),
            _FakeItem("test_gate.py::test_sqlite", postgres=False),
        ]  # type: ignore[arg-type]
    )
    plugin.pytest_runtest_logreport(
        SimpleNamespace(nodeid="test_gate.py::test_postgres", skipped=True)  # type: ignore[arg-type]
    )
    assert plugin.completion_errors() == [
        "Required PostgreSQL tests skipped: test_gate.py::test_postgres"
    ]
