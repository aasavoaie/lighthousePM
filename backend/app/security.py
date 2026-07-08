import secrets

from fastapi import Request
from starlette.responses import JSONResponse, Response

from app.config import Settings

AUTH_EXEMPT_PATHS = frozenset({"/health", "/ready"})


async def enforce_local_api_auth(request: Request, settings: Settings) -> Response | None:
    """Require the Electron-generated bearer token when configured."""
    expected_token = settings.lighthouse_api_token.strip()
    if not expected_token or request.url.path in AUTH_EXEMPT_PATHS:
        return None

    authorization = request.headers.get("authorization", "")
    scheme, _, provided_token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not secrets.compare_digest(provided_token, expected_token):
        return JSONResponse(
            status_code=401,
            content={"detail": "Local API authentication failed."},
            headers={"Cache-Control": "no-store"},
        )
    return None
