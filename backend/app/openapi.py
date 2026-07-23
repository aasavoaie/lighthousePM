from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.security import RouteSecurityClass, route_security_class


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


def _apply_route_security(openapi_schema: dict[str, Any], app: FastAPI) -> None:
    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes[BEARER_SCHEME_NAME] = BEARER_SCHEME

    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        for method in route.methods & APPLICATION_METHODS:
            operation = openapi_schema["paths"][route.path][method.lower()]
            security_class = route_security_class((method, route.path))
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
