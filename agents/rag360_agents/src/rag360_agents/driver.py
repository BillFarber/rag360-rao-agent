import base64
import json
import logging

import time
from typing import Any, Literal, Optional

from httpx import AsyncClient, BasicAuth, DigestAuth
from rao_agent.context.config import ContextAgentConfig

from rao_agent.utils.http import safe_http_client

logger = logging.getLogger(__name__)

LOCAL_MARKLOGIC_BASIC_SSL_URL = "https://host.docker.internal:8004"
LOCAL_MARKLOGIC_DIGEST_URL = "http://host.docker.internal:8003"
LOCAL_MARKLOGIC_OAUTH_URL = "http://host.docker.internal:8006"
MARKLOGIC_AUTH: Literal["api_key", "basic", "digest", "jwt"] = "jwt"


class MarkLogicAgentConfig(ContextAgentConfig):
    """Shared MarkLogic connection config inherited by all RAG360 context agents."""

    auth_method: str = MARKLOGIC_AUTH
    marklogic_url: str = (
        LOCAL_MARKLOGIC_BASIC_SSL_URL
        if MARKLOGIC_AUTH == "basic"
        else (
            LOCAL_MARKLOGIC_DIGEST_URL
            if MARKLOGIC_AUTH == "digest"
            else LOCAL_MARKLOGIC_OAUTH_URL
        )
    )
    marklogic_username: Optional[str] = None
    marklogic_password: Optional[str] = None
    auth_url: Optional[str] = None
    api_key: Optional[str] = None
    jwt_token: Optional[str] = None
    transport_verify: bool = MARKLOGIC_AUTH != "basic"


def build_marklogic_connection_from_headers(
    headers: dict,
    auth_method: str,
    marklogic_url: str,
    marklogic_username: Optional[str] = None,
    marklogic_password: Optional[str] = None,
    auth_url: Optional[str] = None,
    api_key: Optional[str] = None,
    jwt_token: Optional[str] = None,
    transport_verify: bool = True,
) -> tuple["MarkLogicConnection | None", "str | None"]:
    """Parse the incoming Authorization header and build a MarkLogicConnection.

    For digest/basic auth: expects `Authorization: Bearer <base64(user:pass)>`.
    For jwt auth: expects `Authorization: Bearer <token>`.

    Returns (connection, None) on success or (None, error_message) on failure.
    """
    auth_header = headers.get("authorization") or headers.get(
        "Authorization", ""
    )
    bearer_value = (
        auth_header[7:] if auth_header.lower().startswith("bearer ") else None
    )

    username: Optional[str] = marklogic_username
    password: Optional[str] = marklogic_password
    resolved_jwt: Optional[str] = jwt_token

    if auth_method == "jwt":
        if bearer_value:
            resolved_jwt = bearer_value
            logger.info("jwt_token source=request Authorization Bearer header")
        else:
            logger.error(
                "MARKLOGIC_AUTH is 'jwt' but no Authorization Bearer header was provided"
            )
            return (
                None,
                "Error: Authorization Bearer token is required but was not provided.",
            )

    elif auth_method in ("basic", "digest"):
        if bearer_value:
            try:
                decoded = base64.b64decode(bearer_value).decode()
                username, password = decoded.split(":", 1)
                logger.info(
                    "%s auth credentials source=request Authorization Bearer header",
                    auth_method,
                )
            except Exception:
                logger.error(
                    "MARKLOGIC_AUTH is '%s' but Authorization Bearer value could not be "
                    "base64-decoded as username:password",
                    auth_method,
                )
                return (
                    None,
                    "Error: Authorization Bearer value could not be decoded as base64 username:password.",
                )
        else:
            logger.error(
                "MARKLOGIC_AUTH is '%s' but no Authorization Bearer header was provided",
                auth_method,
            )
            return (
                None,
                f"Error: Authorization Bearer header with base64 credentials is required for "
                f"{auth_method} auth but was not provided.",
            )

    return (
        MarkLogicConnection(
            base_url=marklogic_url,
            auth_method=auth_method,
            auth_url=auth_url,
            api_key=api_key,
            username=username,
            password=password,
            jwt_token=resolved_jwt,
            transport_verify=transport_verify,
        ),
        None,
    )


class MarkLogicConnection:
    def __init__(
        self,
        base_url: str,
        auth_method: str = "api_key",
        auth_url: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        jwt_token: Optional[str] = None,
        transport_verify: bool = True,
    ):
        self._client = AsyncClient(verify=transport_verify)
        self._client.base_url = base_url

        if auth_method == "digest":
            assert username is not None and password is not None
            self._client.auth = DigestAuth(username, password)
            self._auth_expires = float("inf")
            self._auth_url = None
            self._api_key = None
        elif auth_method == "basic":
            assert username is not None and password is not None
            self._client.auth = BasicAuth(username, password)
            self._auth_expires = float("inf")
            self._auth_url = None
            self._api_key = None
        elif auth_method == "jwt":
            assert jwt_token is not None
            self._client.headers = {"Authorization": f"Bearer {jwt_token}"}
            self._auth_expires = float("inf")
            self._auth_url = None
            self._api_key = None
        else:
            self._auth_expires = 0
            self._auth_url = auth_url
            self._api_key = api_key

    async def retrieve_raw(self, body: dict) -> Any:
        """POST body directly to /v1/retrieve and return the full JSON response."""
        await self._ensure_auth()
        response = await self._client.post("/v1/retrieve", json=body)
        response.raise_for_status()
        return response.json()

    async def augment_raw(self, body: dict) -> Any:
        """POST body directly to /v1/augment and return the full JSON response."""
        await self._ensure_auth()
        response = await self._client.post("/v1/augment", json=body)
        response.raise_for_status()
        return response.json()

    async def definition(self) -> dict:
        await self._ensure_auth()
        response = await self._client.get("/v1/retrieve/definition")
        response.raise_for_status()
        return response.json()

    async def augment(self, ids: list[str]) -> list[str]:
        await self._ensure_auth()
        response = await self._client.get(
            "/v1/augment", params={"URIs": json.dumps(ids)}
        )
        response.raise_for_status()
        docs = []
        for doc in response.json()["documents"]:
            content = doc["document"]
            if isinstance(content, dict):
                docs.append(json.dumps(content))
            else:
                docs.append(content)
        return docs

    async def _ensure_auth(self):
        if self._auth_expires > time.monotonic():
            return

        async with safe_http_client() as session:
            response = await session.post(
                self._auth_url,
                data={"grant_type": "apikey", "key": self._api_key},
            )
            response.raise_for_status()
            doc = response.json()
            token = doc["access_token"]
            expiry_minutes = doc["expires_in"]
            self._client.headers = {"Authorization": f"Bearer {token}"}
            self._auth_expires = time.monotonic() + (60 * expiry_minutes * 0.9)
