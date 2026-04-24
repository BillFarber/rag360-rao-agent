import json
import logging
import os
from time import time
from typing import Any, Literal, Optional
from uuid import uuid4

import httpx
from rao_agent.agent import Agent
from rao_agent.configure import agent
from rao_agent.context.agent import ContextAgent
from rao_agent.exceptions import AutheticationException
from rao_agent.manager import Manager
from rao_agent.memory import QuestionMemory
from rao_agent.memory import Chunk, Context

from nuclia_arag_api.v1.router import router
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from rag360_agents.driver import (
    MarkLogicAgentConfig,
    build_marklogic_connection_from_headers,
)

logger = logging.getLogger(__name__)


class RetrieveDefinitionAgentConfig(MarkLogicAgentConfig):
    module: Literal["retrieve-definition"] = "retrieve-definition"


@agent(
    id="retrieve-definition",
    agent_type="context",
    title="Retrieve Definition",
    description="Get the RetrieveDefinition from MarkLogic.",
    config_schema=RetrieveDefinitionAgentConfig,
)
class RetrieveDefinitionAgent(
    ContextAgent, Agent[RetrieveDefinitionAgentConfig]
):
    async def getRetrieveDefinition(
        self,
        memory: QuestionMemory,
        manager: Manager,
        question: Optional[str] = "",
        question_uuid: Optional[str] = None,
    ) -> Context:
        logger.info(
            "getRetrieveDefinition called\n\tmarklogic_url=%s",
            (self.config.marklogic_url if self.config.marklogic_url else None),
        )

        def _error_context(text: str) -> Context:
            return Context(
                agent_id=self.config.id or "retrieve-definition",
                original_question_uuid=memory.original_question_uuid,
                actual_question_uuid=question_uuid or uuid4().hex,
                question=question or "",
                source="retrieve-definition",
                agent="retrieve-definition",
                title=self.config.title,
                chunks=[Chunk(chunk_id="definition", text=text)],
            )

        marklogic_client, error = build_marklogic_connection_from_headers(
            headers=memory.headers,
            auth_method=self.config.auth_method,
            marklogic_url=self.config.marklogic_url,
            marklogic_username=self.config.marklogic_username,
            marklogic_password=self.config.marklogic_password,
            auth_url=self.config.auth_url,
            api_key=self.config.api_key,
            jwt_token=self.config.jwt_token,
            transport_verify=self.config.transport_verify,
        )
        if marklogic_client is None:
            logger.error(
                "build_marklogic_connection_from_headers failed: %s", error
            )
            raise AutheticationException(error)

        response = await marklogic_client.definition()
        definition_text = json.dumps(response, indent=2)

        return Context(
            agent_id=self.config.id or "retrieve-definition",
            original_question_uuid=memory.original_question_uuid,
            actual_question_uuid=question_uuid or uuid4().hex,
            question=question or "",
            source="retrieve-definition",
            agent="retrieve-definition",
            title=self.config.title,
            chunks=[Chunk(chunk_id="definition", text=definition_text)],
        )

    async def _get_question_context(
        self,
        memory: QuestionMemory,
        manager: Manager,
        question_uuid: str,
        question: str,
        flow_id: str,
        extra_context: Optional[dict[str, Any]] = None,
    ) -> list[tuple[str, str]]:
        t0 = time()
        context = await self.getRetrieveDefinition(
            memory=memory,
            manager=manager,
            question=question,
            question_uuid=question_uuid,
        )
        missing = await self.save_ctx_and_return_missing(
            context=context,
            question=question,
            memory=memory,
            manager=manager,
            flow_id=flow_id,
        )
        await memory.add_step(
            step_module=self.config.module,
            step_title=self.step_title("Retrieve Definition"),
            step_agent_path=f"/context/{self.config.id or 'retrieve-definition'}",
            step_value=question,
            timeit=time() - t0,
            input_nuclia_tokens=0,
            output_nuclia_tokens=0,
            error=None,
        )
        return [missing] if missing is not None else []


def _keycloak_urls(request: Request) -> tuple[str, str]:
    """
    Return (resource_base, proxy_base) where proxy_base is the base URL for
    our /authorize and /token proxy endpoints (i.e. this server).
    The Keycloak HTTPS URL (KEYCLOAK_EXTERNAL_URL) is only used internally to
    proxy requests — VS Code communicates with us over plain HTTP.
    """
    base = str(request.base_url).rstrip("/")
    return base, base


@router.get("/.well-known/oauth-protected-resource")
async def rag360_oauth_protected_resource(request: Request):
    """
    OAuth 2.0 Protected Resource Metadata (RFC 9728).

    Points MCP clients at this server's /authorize and /token proxy endpoints
    so they never need to deal with Keycloak's self-signed TLS certificate.
    """
    logger.info("rag360_oauth_protected_resource")
    resource_base, proxy_base = _keycloak_urls(request)

    return {
        "resource": resource_base,
        "authorization_servers": [proxy_base],
        "scopes_supported": ["openid", "profile", "email"],
    }


@router.get("/.well-known/oauth-authorization-server")
async def rag360_oauth_authorization_server(request: Request):
    """
    OAuth 2.0 Authorization Server Metadata (RFC 8414).

    Advertises our HTTP proxy endpoints so VS Code uses plain HTTP for all
    OAuth traffic.  /authorize redirects the browser to Keycloak; /token
    proxies code-exchange requests to Keycloak.
    """
    logger.info("rag360_oauth_authorization_server")
    _, proxy_base = _keycloak_urls(request)
    realm = os.environ.get(
        "KEYCLOAK_EXTERNAL_URL", "https://localhost:8443/realms/RAG360"
    ).rstrip("/")

    return {
        "issuer": realm,
        "authorization_endpoint": f"{proxy_base}/authorize",
        "token_endpoint": f"{proxy_base}/token",
        "jwks_uri": f"{realm}/protocol/openid-connect/certs",
        "response_types_supported": ["code"],
        "grant_types_supported": [
            "authorization_code",
            "client_credentials",
            "refresh_token",
        ],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["openid", "profile", "email"],
    }


@router.get("/authorize")
async def rag360_authorize(request: Request):
    """
    Proxy authorize endpoint — redirects the browser to Keycloak's real
    authorization endpoint, preserving all query parameters.
    Uses KEYCLOAK_EXTERNAL_URL (default: https://localhost:8443/realms/RAG360)
    because the redirect target must be reachable from the user's browser.
    """
    logger.info("rag360_authorize")
    realm = os.environ.get(
        "KEYCLOAK_EXTERNAL_URL", "https://localhost:8443/realms/RAG360"
    ).rstrip("/")
    keycloak_auth = f"{realm}/protocol/openid-connect/auth"
    params = str(request.url.query)
    redirect_url = f"{keycloak_auth}?{params}" if params else keycloak_auth
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/token")
async def rag360_token(request: Request):
    """
    Proxy token endpoint — forwards the code-exchange request to Keycloak
    and returns the response.  Allows VS Code to stay on plain HTTP.
    Uses KEYCLOAK_REALM_URL (default: https://keycloak:8443/realms/RAG360)
    because this request is made from inside the container.
    """
    logger.info("rag360_token")
    # The agent container is on a different Docker network from Keycloak.
    # Use KEYCLOAK_INTERNAL_URL (via host.docker.internal) to reach Keycloak
    # from inside the container.  Defaults to https://host.docker.internal:8443.
    realm = os.environ.get(
        "KEYCLOAK_INTERNAL_URL", "https://host.docker.internal:8443/realms/RAG360"
    ).rstrip("/")
    keycloak_token = f"{realm}/protocol/openid-connect/token"
    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in ("content-type", "authorization")
    }
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(keycloak_token, content=body, headers=headers)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
