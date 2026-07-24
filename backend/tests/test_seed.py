from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import seed
from app.db.base import Base
from app.models import Issue, IssueHistory, Release


def test_seed_main_smoke_and_idempotent(monkeypatch) -> None:
    """Smoke test for local seed script (CI-ready when CI is added)."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

    def _fake_init_db() -> None:
        Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(seed, "init_db", _fake_init_db)
    monkeypatch.setattr(seed, "SessionLocal", SessionLocal)

    # First run inserts baseline sample rows.
    seed.main()

    with SessionLocal() as session:
        release_count = session.scalar(select(Release.id).where(Release.release_id == "REL-DEMO-1"))
        issues_count = len(session.scalars(select(Issue.issue_key).where(Issue.release_id == "REL-DEMO-1")).all())
        history_count = len(session.scalars(select(IssueHistory.id).where(IssueHistory.issue_key == "DEMO-3")).all())

    assert release_count is not None
    assert issues_count == 3
    assert history_count == 3

    # Second run should be safe and idempotent.
    seed.main()

    with SessionLocal() as session:
        issues_count_again = len(session.scalars(select(Issue.issue_key).where(Issue.release_id == "REL-DEMO-1")).all())
        history_count_again = len(session.scalars(select(IssueHistory.id).where(IssueHistory.issue_key == "DEMO-3")).all())

    assert issues_count_again == 3
    assert history_count_again == 3
