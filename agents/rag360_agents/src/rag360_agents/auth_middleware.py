"""Starlette ASGI middleware that enforces Bearer token presence on agent endpoints."""
import base64
import json
import logging
import time

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from rag360_agents.driver import MARKLOGIC_AUTH

logger = logging.getLogger(__name__)

_AGENT_PATH_PREFIX = "/api/v1/agent/"
# Allow tokens that expired within this many seconds (handles minor clock skew).
_CLOCK_SKEW_TOLERANCE_S = 10


def _is_jwt_expired(token: str) -> bool:
    """Return True if the JWT exp claim is in the past (plus clock-skew tolerance).

    Decodes only the payload claims — does NOT verify the signature. This is
    intentional: we use it only for an early-rejection optimisation. MarkLogic
    still performs the authoritative cryptographic validation on every request.
    Returns False on any decode error so malformed tokens are passed through to
    MarkLogic for proper rejection.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        # base64url padding: use negative modulo to avoid adding 4 chars when already aligned
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        if exp is None:
            return False
        return time.time() > exp + _CLOCK_SKEW_TOLERANCE_S
    except Exception:
        return False


class BearerTokenMiddleware:
    """Return HTTP 401 when requests to agent endpoints lack or carry an expired Bearer token.

    Only active when the configured auth method requires a Bearer token
    (i.e., MARKLOGIC_AUTH != "api_key"). CORS preflight (OPTIONS) requests
    are passed through so they can be handled by upstream CORS middleware.

    Token expiry is detected by reading the JWT ``exp`` claim without signature
    verification — MarkLogic remains the authoritative validator. This catches
    the common case of a cached expired token so that VS Code re-triggers the
    PKCE login flow instead of silently returning a MarkLogic error string.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and MARKLOGIC_AUTH != "api_key":
            path = scope.get("path", "")
            method = scope.get("method", "")
            if path.startswith(_AGENT_PATH_PREFIX) and method != "OPTIONS":
                headers = Headers(scope=scope)
                auth_header = headers.get("authorization", "")

                # Derive the base URL from the request scope so the
                # resource_metadata hint is correct regardless of host/port.
                server = scope.get("server")
                scheme = scope.get("scheme", "http")
                host = (
                    f"{server[0]}:{server[1]}"
                    if server
                    else headers.get("host", "localhost")
                )
                resource_metadata_url = (
                    f"{scheme}://{host}/.well-known/oauth-protected-resource"
                )

                if not auth_header.lower().startswith("bearer "):
                    logger.warning(
                        "Rejected %s %s — missing Authorization Bearer header",
                        method,
                        path,
                    )
                    response = JSONResponse(
                        {"detail": "Authorization Bearer token is required."},
                        status_code=401,
                        headers={
                            "WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata_url}"'
                        },
                    )
                    await response(scope, receive, send)
                    return

                token = auth_header[7:]
                if _is_jwt_expired(token):
                    logger.warning(
                        "Rejected %s %s — Bearer token has expired",
                        method,
                        path,
                    )
                    response = JSONResponse(
                        {"detail": "Access token has expired. Please re-authenticate."},
                        status_code=401,
                        headers={
                            "WWW-Authenticate": (
                                f'Bearer resource_metadata="{resource_metadata_url}",'
                                ' error="invalid_token",'
                                ' error_description="The access token has expired"'
                            )
                        },
                    )
                    await response(scope, receive, send)
                    return

        await self.app(scope, receive, send)
