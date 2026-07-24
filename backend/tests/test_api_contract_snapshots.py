from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.services.sync_service import SyncAlreadyRunningError
import tests.api_contract_snapshots as api_contract_snapshots
from tests.api_contract_snapshots import (
    API_CONTRACT_ROOT,
    API_CONTRACT_UPDATE_ENV,
    ApiContractSnapshotError,
    assert_api_contract_snapshot,
    load_api_contract_manifest,
    render_json,
)


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db_session() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    configured_app = _configured_app(monkeypatch)
    try:
        with TestClient(configured_app) as client:
            yield client
    finally:
        get_settings.cache_clear()


def _configured_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DEPLOYMENT_MODE", "local-browser")
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:5173")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", "contract-test-token")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN_FILE", "")
    monkeypatch.setenv("JIRA_API_TOKEN", "")
    monkeypatch.setenv("JIRA_API_TOKEN_FILE", "")
    monkeypatch.setenv("JIRA_SYNC_ENABLED", "false")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", "")
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "start_scheduler", lambda settings: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)
    get_settings.cache_clear()
    return main_module.create_app()


def _write_contract_set(
    root: Path,
    contracts: list[dict[str, object]],
    snapshots: dict[str, object],
) -> None:
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        render_json({"version": 1, "contracts": contracts}),
        encoding="utf-8",
    )
    for relative_path, payload in snapshots.items():
        snapshot_path = root / relative_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(render_json(payload), encoding="utf-8")


def _contract(
    contract_id: str = "test.contract",
    snapshot: str = "test.json",
) -> dict[str, object]:
    return {
        "id": contract_id,
        "method": "GET",
        "path": "/test",
        "status_code": 200,
        "snapshot": snapshot,
    }


def test_committed_api_contract_manifest_is_complete_and_safe() -> None:
    contracts = load_api_contract_manifest()

    assert [contract.contract_id for contract in contracts] == [
        "error.authentication.401",
        "error.release-not-found.404",
        "error.sync-already-running.409",
        "error.privileged-validation.422",
        "release.collection.project-scoped.200",
        "release.metrics.populated.200",
        "release.metrics.incomplete-evidence.200",
        "release.signal.stored.200",
        "release.snapshot-comparison.200",
        "sprint.collection.project-scoped.200",
        "sprint.current.project-scoped.200",
        "sprint.metrics.complete-reopen-evidence.200",
        "sprint.metrics.partial-coverage.200",
        "sprint.metrics.inconclusive-coverage.200",
        "sprint.snapshot-comparison.200",
        "configuration.jira.redacted.200",
        "sync.jira.success.200",
    ]


def test_manifest_rejects_missing_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "contracts"
    _write_contract_set(root, [_contract(snapshot="missing.json")], {})

    with pytest.raises(ApiContractSnapshotError, match="missing snapshots"):
        load_api_contract_manifest(root)


@pytest.mark.parametrize(
    ("contracts", "message"),
    [
        (
            [_contract(), _contract(snapshot="second.json")],
            "duplicate contract ids",
        ),
        (
            [_contract(), _contract(contract_id="second.contract")],
            "duplicate snapshot files",
        ),
    ],
)
def test_manifest_rejects_duplicate_entries(
    tmp_path: Path,
    contracts: list[dict[str, object]],
    message: str,
) -> None:
    root = tmp_path / "contracts"
    _write_contract_set(
        root,
        contracts,
        {"test.json": {"ok": True}, "second.json": {"ok": True}},
    )

    with pytest.raises(ApiContractSnapshotError, match=message):
        load_api_contract_manifest(root)


def test_manifest_rejects_orphaned_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "contracts"
    _write_contract_set(
        root,
        [_contract()],
        {"test.json": {"ok": True}, "orphan.json": {"ok": False}},
    )

    with pytest.raises(ApiContractSnapshotError, match="orphaned snapshots"):
        load_api_contract_manifest(root)


def test_manifest_rejects_noncanonical_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "contracts"
    _write_contract_set(root, [_contract()], {"test.json": {"ok": True}})
    (root / "test.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    with pytest.raises(ApiContractSnapshotError, match="not canonically formatted"):
        load_api_contract_manifest(root)


@pytest.mark.parametrize(
    "payload",
    [
        {"authorization": "redacted"},
        {"detail": "Bearer leaked-secret"},
        {"detail": "Failure in C:\\Users\\developer\\project"},
        {"detail": "postgresql://user:secret@database/app"},
    ],
)
def test_manifest_rejects_sensitive_or_machine_local_values(
    tmp_path: Path,
    payload: object,
) -> None:
    root = tmp_path / "contracts"
    _write_contract_set(root, [_contract()], {"test.json": payload})

    with pytest.raises(ApiContractSnapshotError, match="Sensitive"):
        load_api_contract_manifest(root)


def test_401_authentication_payload_matches_contract(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/config/jira")

    assert_api_contract_snapshot(
        "error.authentication.401",
        status_code=response.status_code,
        payload=response.json(),
    )


def test_404_release_not_found_payload_matches_contract(api_client: TestClient) -> None:
    response = api_client.get("/releases/UNKNOWN/metrics")

    assert_api_contract_snapshot(
        "error.release-not-found.404",
        status_code=response.status_code,
        payload=response.json(),
    )


def test_409_sync_running_payload_matches_contract(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_sync_running(self, session: Session) -> dict[str, int | str]:
        raise SyncAlreadyRunningError("Jira sync is already running")

    monkeypatch.setattr(
        "app.services.sync_service.SyncService.sync_from_jira",
        fake_sync_running,
    )
    response = api_client.post("/sync/jira")

    assert_api_contract_snapshot(
        "error.sync-already-running.409",
        status_code=response.status_code,
        payload=response.json(),
    )


def test_422_privileged_validation_payload_matches_contract(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.put(
        "/config/jira",
        headers={"Authorization": "Bearer contract-test-token"},
        json={"jira_api_token": {"submitted": "candidate-secret"}},
    )

    assert_api_contract_snapshot(
        "error.privileged-validation.422",
        status_code=response.status_code,
        payload=response.json(),
    )


def test_snapshot_assertion_compares_serialized_key_order(tmp_path: Path) -> None:
    root = tmp_path / "contracts"
    _write_contract_set(
        root,
        [_contract()],
        {"test.json": {"first": 1, "second": 2}},
    )

    with pytest.raises(AssertionError, match="API contract 'test.contract' changed"):
        assert_api_contract_snapshot(
            "test.contract",
            status_code=200,
            payload={"second": 2, "first": 1},
            root=root,
        )


def test_explicit_update_mode_atomically_replaces_committed_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "contracts"
    _write_contract_set(root, [_contract()], {"test.json": {"before": True}})
    monkeypatch.setattr(api_contract_snapshots, "API_CONTRACT_ROOT", root)
    monkeypatch.setenv(API_CONTRACT_UPDATE_ENV, "1")

    assert_api_contract_snapshot(
        "test.contract",
        status_code=200,
        payload={"after": True},
        root=root,
    )

    assert (root / "test.json").read_text(encoding="utf-8") == render_json(
        {"after": True}
    )
    assert not (root / ".test.json.tmp").exists()


def test_update_mode_cannot_rewrite_an_unapproved_contract_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "contracts"
    original = {"first": 1, "second": 2}
    _write_contract_set(root, [_contract()], {"test.json": original})
    monkeypatch.setenv(API_CONTRACT_UPDATE_ENV, "1")

    with pytest.raises(AssertionError, match="API contract 'test.contract' changed"):
        assert_api_contract_snapshot(
            "test.contract",
            status_code=200,
            payload={"changed": True},
            root=root,
        )

    assert (root / "test.json").read_text(encoding="utf-8") == render_json(original)


def test_update_mode_rejects_sensitive_payload_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "contracts"
    original = {"safe": True}
    _write_contract_set(root, [_contract()], {"test.json": original})
    monkeypatch.setattr(api_contract_snapshots, "API_CONTRACT_ROOT", root)
    monkeypatch.setenv(API_CONTRACT_UPDATE_ENV, "1")

    with pytest.raises(ApiContractSnapshotError, match="Sensitive"):
        assert_api_contract_snapshot(
            "test.contract",
            status_code=200,
            payload={"password": "must-not-be-written"},
            root=root,
        )

    assert (root / "test.json").read_text(encoding="utf-8") == render_json(original)


def test_contract_root_is_committed_under_backend_tests() -> None:
    assert API_CONTRACT_ROOT.relative_to(Path(__file__).resolve().parent) == Path(
        "contracts/api"
    )
