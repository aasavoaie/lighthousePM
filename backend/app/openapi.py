from collections.abc import Callable, Iterable, Iterator
from typing import Any, NamedTuple, cast

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.security import RouteSecurityClass, route_security_class

_fastapi_iter_route_contexts: Callable[[Iterable[Any]], Iterable[Any]] | None
try:
    from fastapi.routing import iter_route_contexts as _imported_iter_route_contexts  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - exercised by older local FastAPI installs.
    _fastapi_iter_route_contexts = None
else:
    _fastapi_iter_route_contexts = cast(
        Callable[[Iterable[Any]], Iterable[Any]],
        _imported_iter_route_contexts,
    )


APPLICATION_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
BEARER_SCHEME_NAME = "BearerAuth"
BEARER_SCHEME = {
    "type": "http",
    "scheme": "bearer",
    "description": (
        "LighthousePM API token required whenever authentication is enabled "
        "for the active deployment mode."
    ),
}
AUTHENTICATION_ERROR_RESPONSE = {
    "description": "API bearer authentication failed.",
    "content": {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
        }
    },
}


class _RouteContext(NamedTuple):
    route: APIRoute
    methods: set[str]
    path: str


def _iter_route_contexts(routes: Iterable[Any]) -> Iterator[_RouteContext]:
    if _fastapi_iter_route_contexts is not None:
        for route_context in _fastapi_iter_route_contexts(routes):
            route = route_context.route
            if isinstance(route, APIRoute):
                yield _RouteContext(
                    route=route,
                    methods=set(route_context.methods or ()),
                    path=route_context.path or "",
                )
        return

    for route in routes:
        if isinstance(route, APIRoute):
            yield _RouteContext(
                route=route,
                methods=set(route.methods or ()),
                path=route.path,
            )


def _apply_route_security(openapi_schema: dict[str, Any], app: FastAPI) -> None:
    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes[BEARER_SCHEME_NAME] = BEARER_SCHEME

    for route_context in _iter_route_contexts(app.routes):
        route = route_context.route
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        methods = route_context.methods
        if not methods:
            continue
        path = route_context.path
        if not path:
            continue
        for method in methods & APPLICATION_METHODS:
            operation = openapi_schema["paths"][path][method.lower()]
            security_class = route_security_class((method, path))
            if security_class == RouteSecurityClass.PUBLIC_HEALTH:
                operation.pop("security", None)
                operation["responses"].pop("401", None)
                continue

            operation["security"] = [{BEARER_SCHEME_NAME: []}]
            operation["responses"].setdefault(
                "401",
                AUTHENTICATION_ERROR_RESPONSE,
            )


def install_openapi_security(app: FastAPI) -> None:
    """Add deployment-aware bearer metadata without a second auth dependency."""

    default_openapi: Callable[[], dict[str, Any]] = app.openapi

    def openapi_with_security() -> dict[str, Any]:
        openapi_schema = default_openapi()
        _apply_route_security(openapi_schema, app)
        return openapi_schema

    # FastAPI intentionally supports replacing this instance hook at runtime,
    # while its type declaration exposes ``openapi`` as a class method.
    setattr(app, "openapi", openapi_with_security)
