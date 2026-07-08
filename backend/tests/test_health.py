from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.health import get_db_session
from app.main import app


def test_health_endpoint_contract() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Jira Release Signals",
        "environment": "dev",
    }


def test_ready_endpoint_checks_database_connectivity() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

    def _override_db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = _override_db_session
    try:
        client = TestClient(app)

        response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "Jira Release Signals",
        "environment": "dev",
        "checks": {"database": "ok"},
    }


def test_ready_endpoint_returns_503_when_database_unavailable() -> None:
    class UnavailableSession:
        def execute(self, statement) -> None:
            raise SQLAlchemyError("database unavailable")

        def close(self) -> None:
            return None

    def _override_db_session():
        session = UnavailableSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = _override_db_session
    try:
        client = TestClient(app)

        response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "service": "Jira Release Signals",
            "environment": "dev",
            "checks": {"database": "unavailable"},
        }
    }
