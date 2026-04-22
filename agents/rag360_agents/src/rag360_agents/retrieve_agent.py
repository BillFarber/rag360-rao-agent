import json
import logging
from time import time
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

import httpx
from rao_agent.agent import Agent
from rao_agent.configure import agent
from rao_agent.context.agent import ContextAgent
from rao_agent.context.config import ContextAgentConfig
from rao_agent.manager import Manager
from rao_agent.memory import Chunk, Context, QuestionMemory

from rag360_agents.driver import build_marklogic_connection_from_headers

logger = logging.getLogger(__name__)

LOCAL_MARKLOGIC_DIGEST_URL = "http://host.docker.internal:8003"


class RetrieveAgentConfig(ContextAgentConfig):
    module: Literal["retrieve"] = "retrieve"
    auth_method: str = "digest"
    marklogic_url: str = LOCAL_MARKLOGIC_DIGEST_URL
    marklogic_username: Optional[str] = None
    marklogic_password: Optional[str] = None
    auth_url: Optional[str] = None
    api_key: Optional[str] = None
    jwt_token: Optional[str] = None
    transport_verify: bool = True


@agent(
    id="retrieve",
    agent_type="context",
    title="Retrieve",
    description="Retrieve documents from MarkLogic. Pass a retrieveQuery JSON object as the POST body to /v1/retrieve.",
    config_schema=RetrieveAgentConfig,
)
class RetrieveAgent(ContextAgent, Agent[RetrieveAgentConfig]):
    async def getRetrieve(
        self,
        memory: QuestionMemory,
        manager: Manager,
        question: Optional[str] = "",
        question_uuid: Optional[str] = None,
    ) -> Context:
        agent_id = self.config.id or "retrieve"
        actual_question_uuid = question_uuid or uuid4().hex

        def _error_context(text: str) -> Context:
            return Context(
                agent_id=agent_id,
                original_question_uuid=memory.original_question_uuid,
                actual_question_uuid=actual_question_uuid,
                question=question or "",
                source="retrieve",
                agent="retrieve",
                title=self.config.title,
                chunks=[Chunk(chunk_id="retrieve-error", text=text)],
            )

        logger.info("getRetrieve called\n\tmarklogic_url=%s", self.config.marklogic_url)

        retrieve_query_raw = (getattr(memory, "arguments", None) or {}).get("retrieveQuery")
        if not retrieve_query_raw:
            logger.error("getRetrieve: retrieveQuery parameter is missing")
            return _error_context("Error: retrieveQuery parameter is required.")

        try:
            retrieve_query = json.loads(retrieve_query_raw)
        except (json.JSONDecodeError, TypeError):
            logger.error("getRetrieve: retrieveQuery is not valid JSON")
            return _error_context("Error: retrieveQuery must be a valid JSON string.")


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

        try:
            response = await marklogic_client.retrieve_raw(retrieve_query)
        except httpx.HTTPError as exc:
            logger.error("MarkLogic /v1/retrieve request failed: %s", exc)
            return _error_context(f"Error: MarkLogic retrieve request failed: {exc}")

        return Context(
            agent_id=agent_id,
            original_question_uuid=memory.original_question_uuid,
            actual_question_uuid=actual_question_uuid,
            question=question or "",
            source="retrieve",
            agent="retrieve",
            title=self.config.title,
            chunks=[Chunk(chunk_id="retrieve-result", text=json.dumps(response, indent=2))],
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
        context = await self.getRetrieve(
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
            step_title=self.step_title("Retrieve"),
            step_agent_path=f"/context/{self.config.id or 'retrieve'}",
            step_value=question,
            timeit=time() - t0,
            input_nuclia_tokens=0,
            output_nuclia_tokens=0,
            error=None,
        )
        return [missing] if missing is not None else []
