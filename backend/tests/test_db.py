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
