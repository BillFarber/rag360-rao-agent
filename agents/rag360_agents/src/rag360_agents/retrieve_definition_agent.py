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


class RetrieveDefinitionAgentConfig(ContextAgentConfig):
    module: Literal["retrieve-definition"] = "retrieve-definition"
    marklogic_url: str = "http://host.docker.internal:8003"
    marklogic_username: Optional[str] = "admin"
    marklogic_password: Optional[str] = "admin"
    auth_url: Optional[str] = (None,)
    api_key: Optional[str] = (None,)
    jwt_token: Optional[str] = (None,)


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
        # manager.getdriver("marklogic")  # Ensure driver is initialized
        marklogic_client = MarkLogicConnection(
            base_url=self.config.marklogic_url,
            auth_method="digest",
            # auth_url=driver.config.auth_url,
            # api_key="asdf",
            username=self.config.marklogic_username,
            password=self.config.marklogic_password,
            # jwt_token=driver.config.jwt_token,
        )
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
