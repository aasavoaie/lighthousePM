import app.db.init as db_init_module
from app.db.base import Base
from app.db.init import init_db


def test_all_mvp_tables_registered() -> None:
    table_names = set(Base.metadata.tables.keys())
    assert {
        "issues",
        "issue_history",
        "releases",
        "metric_snapshots",
        "release_signals",
    }.issubset(table_names)


def test_init_db_calls_create_all(monkeypatch) -> None:
    called = {"value": False}

    def _fake_create_all(*args, **kwargs) -> None:
        called["value"] = True

    monkeypatch.setattr(Base.metadata, "create_all", _fake_create_all)
    init_db(ensure_compat_columns=False)

    assert called["value"] is True


def test_init_db_compat_columns_include_release_scope_counts(monkeypatch) -> None:
    statements: list[str] = []

    class FakeDialect:
        name = "postgresql"

    class FakeConnection:
        def execute(self, statement) -> None:
            statements.append(str(statement))

    class FakeBegin:
        def __enter__(self) -> FakeConnection:
            return FakeConnection()

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    class FakeEngine:
        dialect = FakeDialect()

        def begin(self) -> FakeBegin:
            return FakeBegin()

    monkeypatch.setattr(db_init_module, "engine", FakeEngine())
    monkeypatch.setattr(Base.metadata, "create_all", lambda *args, **kwargs: None)

    init_db()

    assert any("scope_added_7d_count INTEGER NOT NULL DEFAULT 0" in statement for statement in statements)
    assert any("scope_removed_7d_count INTEGER NOT NULL DEFAULT 0" in statement for statement in statements)
