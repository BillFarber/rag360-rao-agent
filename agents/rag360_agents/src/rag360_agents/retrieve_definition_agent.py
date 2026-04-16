import base64
import json
import logging
from time import time
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from rao_agent.agent import Agent
from rao_agent.configure import agent
from rao_agent.context.agent import ContextAgent
from rao_agent.context.config import ContextAgentConfig
from rao_agent.manager import Manager
from rao_agent.memory import QuestionMemory
from rao_agent.memory import Chunk, Context

from rag360_agents.driver import MarkLogicConnection

logger = logging.getLogger(__name__)

LOCAL_MARKLOGIC_BASIC_SSL_URL = "https://host.docker.internal:8004"
LOCAL_MARKLOGIC_DIGEST_URL = "http://host.docker.internal:8003"
LOCAL_MARKLOGIC_OAUTH_URL = "http://host.docker.internal:8006"
MARKLOGIC_AUTH: Literal["api_key", "basic", "digest", "jwt"] = "digest"


class RetrieveDefinitionAgentConfig(ContextAgentConfig):
    module: Literal["retrieve-definition"] = "retrieve-definition"
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
    def _build_marklogic_connection_from_headers(
        self, headers: dict
    ) -> tuple[MarkLogicConnection | None, str | None]:
        auth_header = headers.get("authorization") or headers.get(
            "Authorization", ""
        )
        bearer_value = (
            auth_header[7:]
            if auth_header.lower().startswith("bearer ")
            else None
        )

        jwt_token: Optional[str] = None
        username: Optional[str] = self.config.marklogic_username
        password: Optional[str] = self.config.marklogic_password

        if self.config.auth_method == "jwt":
            if bearer_value:
                jwt_token = bearer_value
                logger.info(
                    "jwt_token source=request Authorization Bearer header"
                )
            else:
                logger.error(
                    "MARKLOGIC_AUTH is 'jwt' but no Authorization Bearer header was provided"
                )
                return (
                    None,
                    "Error: Authorization Bearer token is required but was not provided.",
                )

        elif self.config.auth_method in ("basic", "digest"):
            if bearer_value:
                try:
                    decoded = base64.b64decode(bearer_value).decode()
                    username, password = decoded.split(":", 1)
                    logger.info(
                        "%s auth credentials source=request Authorization Bearer header",
                        self.config.auth_method,
                    )
                except Exception:
                    logger.error(
                        "MARKLOGIC_AUTH is '%s' but Authorization Bearer value could not be base64-decoded as username:password",
                        self.config.auth_method,
                    )
                    return (
                        None,
                        "Error: Authorization Bearer value could not be decoded as base64 username:password.",
                    )
            else:
                logger.error(
                    "MARKLOGIC_AUTH is '%s' but no Authorization Bearer header was provided",
                    self.config.auth_method,
                )
                return (
                    None,
                    f"Error: Authorization Bearer header with base64 credentials is required for {self.config.auth_method} auth but was not provided.",
                )

        return (
            MarkLogicConnection(
                base_url=self.config.marklogic_url,
                auth_method=self.config.auth_method,
                auth_url=self.config.auth_url,
                api_key=self.config.api_key,
                username=username,
                password=password,
                jwt_token=jwt_token,
                transport_verify=self.config.transport_verify,
            ),
            None,
        )

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
        logger.info("incoming headers: %s", memory.headers)

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

        marklogic_client, error = self._build_marklogic_connection_from_headers(
            memory.headers
        )
        if error:
            return _error_context(error)

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
        extra_context: Optional[Dict[str, Any]] = None,
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
