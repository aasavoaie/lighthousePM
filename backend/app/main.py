from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.api.router import api_router
from app.config import Settings, get_settings
from app.db.init import init_db
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.openapi import install_openapi_security
from app.security import (
    RouteSecurityClass,
    enforce_local_api_auth,
    request_route_security_class,
    validate_route_security_inventory,
)
from app.utils.error_sanitizer import sanitize_error_detail


class RedactingLogFilter(logging.Filter):
    """Redact obvious secrets before records reach configured handlers."""

    def __init__(self, secret_values: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secret_values = tuple(value for value in secret_values if value.strip())

    def filter(self, record: logging.LogRecord) -> bool:
        sanitized = record.getMessage()
        for secret_value in self._secret_values:
            sanitized = sanitized.replace(secret_value, "[REDACTED]")
        record.msg = sanitize_error_detail(sanitized, max_length=1200)
        record.args = ()
        return True


def _configure_logging(level_name: str, secret_values: tuple[str, ...] = ()) -> None:
    """Configure basic application logging with env-driven log level."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    redacting_filter = RedactingLogFilter(secret_values)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(isinstance(existing_filter, RedactingLogFilter) for existing_filter in handler.filters):
            handler.addFilter(redacting_filter)


def _sanitize_privileged_error_detail(detail: object, settings: Settings) -> str:
    if not isinstance(detail, str):
        return "Privileged operation failed."
    sanitized = detail
    for secret_value in (
        settings.effective_lighthouse_api_token,
        settings.effective_jira_api_token,
        settings.effective_postgres_password,
    ):
        if secret_value.strip():
            sanitized = sanitized.replace(secret_value, "[REDACTED]")
    return sanitize_error_detail(sanitized)


@asynccontextmanager
async def app_lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    settings.validate_startup_settings()
    init_db()
    start_scheduler(settings)
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(
        settings.log_level,
        (
            settings.effective_lighthouse_api_token,
            settings.effective_jira_api_token,
            settings.effective_postgres_password,
        ),
    )
    app = FastAPI(title=settings.app_name, lifespan=app_lifespan)

    @app.exception_handler(HTTPException)
    async def protected_http_exception_handler(request: Request, exc: HTTPException):
        if request_route_security_class(request) != RouteSecurityClass.PRIVILEGED_OPERATION:
            return await http_exception_handler(request, exc)
        protected_exception = HTTPException(
            status_code=exc.status_code,
            detail=_sanitize_privileged_error_detail(exc.detail, settings),
            headers=exc.headers,
        )
        response = await http_exception_handler(request, protected_exception)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def protected_validation_exception_handler(request: Request, exc: RequestValidationError):
        if request_route_security_class(request) != RouteSecurityClass.PRIVILEGED_OPERATION:
            return await request_validation_exception_handler(request, exc)
        return JSONResponse(
            status_code=422,
            content={"detail": "Privileged request validation failed."},
            headers={"Cache-Control": "no-store"},
        )

    @app.middleware("http")
    async def local_api_auth_middleware(request, call_next):
        auth_response = await enforce_local_api_auth(request=request, settings=settings)
        if auth_response is not None:
            return auth_response
        response = await call_next(request)
        if request_route_security_class(request) == RouteSecurityClass.PRIVILEGED_OPERATION:
            response.headers["Cache-Control"] = "no-store"
        return response

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origin_list),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router)
    validate_route_security_inventory(app)
    install_openapi_security(app)
    return app


app = create_app()
