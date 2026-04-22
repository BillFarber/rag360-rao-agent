import json
import logging
from time import time
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from rao_agent.agent import Agent
from rao_agent.configure import agent
from rao_agent.context.agent import ContextAgent
from rao_agent.manager import Manager
from rao_agent.memory import QuestionMemory
from rao_agent.memory import Chunk, Context

from rag360_agents.driver import MarkLogicAgentConfig, build_marklogic_connection_from_headers

logger = logging.getLogger(__name__)

LOCAL_MARKLOGIC_BASIC_SSL_URL = "https://host.docker.internal:8004"
LOCAL_MARKLOGIC_DIGEST_URL = "http://host.docker.internal:8003"
LOCAL_MARKLOGIC_OAUTH_URL = "http://host.docker.internal:8006"
MARKLOGIC_AUTH: Literal["api_key", "basic", "digest", "jwt"] = "basic"


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
