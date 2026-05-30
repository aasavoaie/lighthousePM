from collections.abc import Generator

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.repositories.operational_status_repository import OperationalStatusRepository


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    def override_get_db_session() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    original_init_db = main_module.init_db
    main_module.init_db = lambda: None
    try:
        with TestClient(app) as test_client:
            app.state.testing_session_local = testing_session_local
            yield test_client
    finally:
        del app.state.testing_session_local
        main_module.init_db = original_init_db
        app.dependency_overrides.clear()


def test_get_admin_status_empty_state(client: TestClient) -> None:
    response = client.get("/admin/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "Jira Release Signals"
    assert payload["environment"] == "dev"
    assert payload["last_sync_succeeded_at"] is None
    assert payload["last_sync_failed_at"] is None
    assert payload["last_sync_failure_summary"] is None
    assert payload["last_metrics_recompute_at"] is None
    assert payload["last_signal_recompute_at"] is None


def test_get_admin_status_populated_state(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        OperationalStatusRepository.mark_sync_succeeded(session=session)
        OperationalStatusRepository.mark_metrics_recomputed(session=session)
        OperationalStatusRepository.mark_signal_recomputed(session=session)
        OperationalStatusRepository.mark_sync_failed(
            session=session,
            failure_summary="JiraAuthError: Jira authentication failed",
        )
        session.commit()

    response = client.get("/admin/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["last_sync_succeeded_at"] is not None
    assert payload["last_sync_failed_at"] is not None
    assert payload["last_sync_failure_summary"] == "JiraAuthError: Jira authentication failed"
    assert payload["last_metrics_recompute_at"] is not None
    assert payload["last_signal_recompute_at"] is not None
