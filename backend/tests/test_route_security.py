from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from types import SimpleNamespace

import app.api.configuration as configuration_api
import app.main as main_module
from app.config import get_settings
from app.db.session import get_db_session
from app.repositories.release_repository import ReleaseRepository
from app.security import (
    ROUTES_BY_SECURITY_CLASS,
    RouteSecurityClass,
    registered_route_inventory,
    route_security_class,
    validate_route_security_inventory,
)


def _configured_app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_token: str = "launch-secret",
) -> FastAPI:
    monkeypatch.setenv("DEPLOYMENT_MODE", "local-browser")
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:5173")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", api_token)
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN_FILE", "")
    monkeypatch.setenv("JIRA_API_TOKEN", "jira-secret-value")
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "start_scheduler", lambda settings: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)
    get_settings.cache_clear()
    return main_module.create_app()


def _request_path(route_path: str) -> str:
    return (
        route_path.replace("{release_id}", "release-1")
        .replace("{sprint_id}", "sprint-1")
        .replace("{jira_key}", "TEST-1")
        .replace("{depth}", "summary")
    )


def test_registered_routes_have_one_exact_security_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch)
    declared_routes = frozenset().union(*ROUTES_BY_SECURITY_CLASS.values())

    try:
        assert registered_route_inventory(app) == declared_routes
        for route_key in declared_routes:
            assert route_security_class(route_key) in RouteSecurityClass
    finally:
        get_settings.cache_clear()

    assert ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PUBLIC_HEALTH] == frozenset(
        {("GET", "/health")}
    )


def test_new_unclassified_route_fails_inventory_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _configured_app(monkeypatch)
    app.add_api_route("/unclassified", lambda: {"ok": True}, methods=["GET"])

    try:
        with pytest.raises(ValueError, match=r"unclassified: GET /unclassified"):
            validate_route_security_inventory(app)
    finally:
        get_settings.cache_clear()


def test_internal_router_objects_are_not_treated_as_http_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch)
    expected_inventory = registered_route_inventory(app)
    nested_health_route = SimpleNamespace(path="/health", methods={"GET"})
    original_router = SimpleNamespace(routes=[nested_health_route])
    internal_router = SimpleNamespace(original_router=original_router)
    original_router.routes.append(internal_router)
    app.routes.extend([object(), internal_router])

    try:
        assert registered_route_inventory(app) == expected_inventory
        validate_route_security_inventory(app)
    finally:
        get_settings.cache_clear()


def test_duplicate_route_classification_fails_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _configured_app(monkeypatch)
    protected_routes = ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PROTECTED_READ]
    monkeypatch.setitem(
        ROUTES_BY_SECURITY_CLASS,
        RouteSecurityClass.PROTECTED_READ,
        protected_routes | {("GET", "/health")},
    )

    try:
        with pytest.raises(ValueError, match="multiple security classifications"):
            validate_route_security_inventory(app)
    finally:
        get_settings.cache_clear()


def test_stale_route_classification_fails_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _configured_app(monkeypatch)
    protected_routes = ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PROTECTED_READ]
    monkeypatch.setitem(
        ROUTES_BY_SECURITY_CLASS,
        RouteSecurityClass.PROTECTED_READ,
        protected_routes | {("GET", "/retired-route")},
    )

    try:
        with pytest.raises(ValueError, match=r"stale: GET /retired-route"):
            validate_route_security_inventory(app)
    finally:
        get_settings.cache_clear()


def test_any_second_public_route_fails_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _configured_app(monkeypatch)
    docs_route = ("GET", "/docs")
    public_routes = ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PUBLIC_HEALTH]
    protected_routes = ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PROTECTED_READ]
    monkeypatch.setitem(
        ROUTES_BY_SECURITY_CLASS,
        RouteSecurityClass.PUBLIC_HEALTH,
        public_routes | {docs_route},
    )
    monkeypatch.setitem(
        ROUTES_BY_SECURITY_CLASS,
        RouteSecurityClass.PROTECTED_READ,
        protected_routes - {docs_route},
    )

    try:
        with pytest.raises(ValueError, match="GET /health must be the only public route"):
            validate_route_security_inventory(app)
    finally:
        get_settings.cache_clear()


def test_every_nonpublic_route_rejects_an_unauthenticated_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch)
    nonpublic_routes = (
        ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PROTECTED_READ]
        | ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PRIVILEGED_OPERATION]
    )

    try:
        with TestClient(app) as client:
            for method, route_path in sorted(nonpublic_routes):
                response = client.request(method, _request_path(route_path))
                assert response.status_code == 401, f"{method} {route_path} was not protected"
                assert response.headers["cache-control"] == "no-store"
    finally:
        get_settings.cache_clear()


def test_correct_token_accesses_both_protected_classes_and_public_health_needs_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch)

    try:
        with TestClient(app) as client:
            health_response = client.get("/health")
            docs_response = client.get(
                "/docs",
                headers={"Authorization": "Bearer launch-secret"},
            )
            config_response = client.get(
                "/config/jira",
                headers={"Authorization": "Bearer launch-secret"},
            )
    finally:
        get_settings.cache_clear()

    assert health_response.status_code == 200
    assert docs_response.status_code == 200
    assert config_response.status_code == 200
    assert config_response.headers["cache-control"] == "no-store"
    assert "launch-secret" not in config_response.text
    assert "jira-secret-value" not in config_response.text


def test_anonymous_local_development_privileged_response_is_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch, api_token="")

    try:
        with TestClient(app) as client:
            response = client.get("/config/jira")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_privileged_http_and_validation_errors_are_no_store_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_update(_update) -> None:
        raise ValueError("failure launch-secret api_token=route-secret")

    monkeypatch.setattr(configuration_api, "update_jira_configuration", fail_update)
    app = _configured_app(monkeypatch)
    authorization = {"Authorization": "Bearer launch-secret"}

    try:
        with TestClient(app) as client:
            service_error = client.put("/config/jira", headers=authorization, json={})
            validation_error = client.put(
                "/config/jira",
                headers=authorization,
                json={"jira_api_token": {"submitted": "candidate-secret"}},
            )
    finally:
        get_settings.cache_clear()

    assert service_error.status_code == 400
    assert service_error.headers["cache-control"] == "no-store"
    assert "launch-secret" not in service_error.text
    assert "route-secret" not in service_error.text
    assert "[REDACTED]" in service_error.text
    assert validation_error.status_code == 422
    assert validation_error.json() == {"detail": "Privileged request validation failed."}
    assert validation_error.headers["cache-control"] == "no-store"
    assert "candidate-secret" not in validation_error.text


def test_authenticated_unsupported_method_remains_method_not_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch)

    try:
        with TestClient(app) as client:
            response = client.delete(
                "/config/jira",
                headers={"Authorization": "Bearer launch-secret"},
            )
            unauthenticated_health_post = client.post("/health")
            authenticated_health_post = client.post(
                "/health",
                headers={"Authorization": "Bearer launch-secret"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 405
    assert unauthenticated_health_post.status_code == 401
    assert authenticated_health_post.status_code == 405


def test_protected_release_read_does_not_require_a_mutating_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _configured_app(monkeypatch)
    read_only_session = object()

    def provide_read_only_session():
        yield read_only_session

    def list_releases(*, session, project_key, skip, limit):
        assert session is read_only_session
        assert project_key is None
        assert skip == 0
        assert limit == 50
        return [], 0

    app.dependency_overrides[get_db_session] = provide_read_only_session
    monkeypatch.setattr(ReleaseRepository, "list_releases", list_releases)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/releases",
                headers={"Authorization": "Bearer launch-secret"},
            )
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == {"items": [], "skip": 0, "limit": 50, "total": 0}
