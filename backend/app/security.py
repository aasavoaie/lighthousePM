import secrets
from enum import StrEnum
from typing import TypeAlias

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

from app.config import Settings

RouteSecurityKey: TypeAlias = tuple[str, str]


class RouteSecurityClass(StrEnum):
    PUBLIC_HEALTH = "public_health"
    PROTECTED_READ = "protected_read"
    PRIVILEGED_OPERATION = "privileged_operation"


ROUTES_BY_SECURITY_CLASS: dict[RouteSecurityClass, frozenset[RouteSecurityKey]] = {
    RouteSecurityClass.PUBLIC_HEALTH: frozenset({("GET", "/health")}),
    RouteSecurityClass.PROTECTED_READ: frozenset(
        {
            ("GET", "/openapi.json"),
            ("HEAD", "/openapi.json"),
            ("GET", "/docs"),
            ("HEAD", "/docs"),
            ("GET", "/docs/oauth2-redirect"),
            ("HEAD", "/docs/oauth2-redirect"),
            ("GET", "/redoc"),
            ("HEAD", "/redoc"),
            ("GET", "/releases"),
            ("GET", "/releases/{release_id}"),
            ("GET", "/releases/{release_id}/issues"),
            ("GET", "/issues/{jira_key}"),
            ("GET", "/releases/{release_id}/metrics"),
            ("GET", "/releases/{release_id}/charts"),
            ("GET", "/releases/{release_id}/snapshot-comparison"),
            ("GET", "/releases/{release_id}/snapshot-change-history"),
            ("GET", "/releases/{release_id}/reports/overview.pdf"),
            ("GET", "/reports/documentation.pdf"),
            ("GET", "/releases/{release_id}/reports/{depth}.pdf"),
            ("GET", "/sprints/{sprint_id}/reports/{depth}.pdf"),
            ("GET", "/releases/{release_id}/signal"),
            ("GET", "/sprints"),
            ("GET", "/sprints/current"),
            ("GET", "/sprints/{sprint_id}"),
            ("GET", "/sprints/{sprint_id}/issues"),
            ("GET", "/sprints/{sprint_id}/metrics"),
            ("GET", "/sprints/{sprint_id}/snapshot-comparison"),
            ("GET", "/sprints/{sprint_id}/snapshot-change-history"),
        }
    ),
    RouteSecurityClass.PRIVILEGED_OPERATION: frozenset(
        {
            ("GET", "/admin/status"),
            ("GET", "/config/jira"),
            ("PUT", "/config/jira"),
            ("POST", "/config/jira/test"),
            ("POST", "/releases/{release_id}/recompute"),
            ("POST", "/releases/recompute-all"),
            ("POST", "/sprints/{sprint_id}/recompute"),
            ("POST", "/sync/jira"),
        }
    ),
}

AUTH_EXEMPT_ROUTES = ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PUBLIC_HEALTH]


def registered_route_inventory(app: FastAPI) -> frozenset[RouteSecurityKey]:
    registered_routes: set[RouteSecurityKey] = set()
    pending_routes = list(app.routes)
    visited_route_ids: set[int] = set()
    while pending_routes:
        route = pending_routes.pop()
        route_id = id(route)
        if route_id in visited_route_ids:
            continue
        visited_route_ids.add(route_id)

        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if isinstance(path, str) and methods:
            registered_routes.update((method.upper(), path) for method in methods)

        nested_routes = getattr(route, "routes", None)
        if isinstance(nested_routes, (list, tuple)):
            pending_routes.extend(nested_routes)

        original_router = getattr(route, "original_router", None)
        included_routes = getattr(original_router, "routes", None)
        if isinstance(included_routes, (list, tuple)):
            pending_routes.extend(included_routes)
    return frozenset(registered_routes)


def route_security_class(route_key: RouteSecurityKey) -> RouteSecurityClass:
    matches = [
        security_class
        for security_class, routes in ROUTES_BY_SECURITY_CLASS.items()
        if route_key in routes
    ]
    if len(matches) != 1:
        method, path = route_key
        raise ValueError(
            f"Route security classification must be exclusive for {method} {path}; "
            f"found {len(matches)} classifications"
        )
    return matches[0]


def validate_route_security_inventory(app: FastAPI) -> None:
    declared_routes: set[RouteSecurityKey] = set()
    duplicate_routes: set[RouteSecurityKey] = set()
    for routes in ROUTES_BY_SECURITY_CLASS.values():
        duplicate_routes.update(declared_routes & routes)
        declared_routes.update(routes)

    if duplicate_routes:
        formatted = ", ".join(f"{method} {path}" for method, path in sorted(duplicate_routes))
        raise ValueError(f"Routes have multiple security classifications: {formatted}")

    expected_public_routes = frozenset({("GET", "/health")})
    public_routes = ROUTES_BY_SECURITY_CLASS[RouteSecurityClass.PUBLIC_HEALTH]
    if public_routes != expected_public_routes:
        raise ValueError("GET /health must be the only public route")

    registered_routes = registered_route_inventory(app)
    unclassified_routes = registered_routes - declared_routes
    stale_routes = declared_routes - registered_routes
    if unclassified_routes or stale_routes:
        details: list[str] = []
        if unclassified_routes:
            details.append(
                "unclassified: "
                + ", ".join(f"{method} {path}" for method, path in sorted(unclassified_routes))
            )
        if stale_routes:
            details.append(
                "stale: " + ", ".join(f"{method} {path}" for method, path in sorted(stale_routes))
            )
        raise ValueError("Route security inventory mismatch (" + "; ".join(details) + ")")


def request_route_security_class(request: Request) -> RouteSecurityClass | None:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if not isinstance(route_path, str):
        return None
    route_key = (request.method.upper(), route_path)
    if route_key not in registered_route_inventory(request.app):
        return None
    return route_security_class(route_key)


async def enforce_local_api_auth(request: Request, settings: Settings) -> Response | None:
    """Require the configured bearer token outside the single health exemption."""
    request_key = (request.method.upper(), request.url.path)
    if request_key in AUTH_EXEMPT_ROUTES or not settings.api_auth_enabled:
        return None

    expected_token = settings.effective_lighthouse_api_token
    authorization = request.headers.get("authorization", "")
    scheme, _, provided_token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not secrets.compare_digest(provided_token, expected_token):
        return JSONResponse(
            status_code=401,
            content={"detail": "API authentication failed."},
            headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"},
        )
    return None
