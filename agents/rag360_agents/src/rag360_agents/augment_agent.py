import json
import logging
from time import time
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

import httpx
from rao_agent.agent import Agent
from rao_agent.configure import agent
from rao_agent.context.agent import ContextAgent
from rao_agent.manager import Manager
from rao_agent.memory import Chunk, Context, QuestionMemory

from rag360_agents.driver import MarkLogicAgentConfig, build_marklogic_connection_from_headers

logger = logging.getLogger(__name__)


class AugmentAgentConfig(MarkLogicAgentConfig):
    module: Literal["augment"] = "augment"


@agent(
    id="augment",
    agent_type="context",
    title="Augment",
    description="Fetch full document content from MarkLogic by URI. Pass an augmentRequest JSON object as the POST body to /v1/augment.",
    config_schema=AugmentAgentConfig,
)
class AugmentAgent(ContextAgent, Agent[AugmentAgentConfig]):
    async def getAugment(
        self,
        memory: QuestionMemory,
        manager: Manager,
        question: Optional[str] = "",
        question_uuid: Optional[str] = None,
    ) -> Context:
        agent_id = self.config.id or "augment"
        actual_question_uuid = question_uuid or uuid4().hex

        def _error_context(text: str) -> Context:
            return Context(
                agent_id=agent_id,
                original_question_uuid=memory.original_question_uuid,
                actual_question_uuid=actual_question_uuid,
                question=question or "",
                source="augment",
                agent="augment",
                title=self.config.title,
                chunks=[Chunk(chunk_id="augment-error", text=text)],
            )

        logger.info("getAugment called\n\tmarklogic_url=%s", self.config.marklogic_url)

        augment_request_raw = (getattr(memory, "arguments", None) or {}).get("augmentRequest")
        if not augment_request_raw:
            logger.error("getAugment: augmentRequest parameter is missing")
            return _error_context("Error: augmentRequest parameter is required.")

        try:
            augment_request = json.loads(augment_request_raw)
        except (json.JSONDecodeError, TypeError):
            logger.error("getAugment: augmentRequest is not valid JSON")
            return _error_context("Error: augmentRequest must be a valid JSON string.")

        # Normalize "uris" → "URIs" — LLM clients often send lowercase despite the description.
        if isinstance(augment_request, dict) and "uris" in augment_request and "URIs" not in augment_request:
            augment_request["URIs"] = augment_request.pop("uris")
            logger.info("getAugment: normalized 'uris' key to 'URIs'")

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
            response = await marklogic_client.augment_raw(augment_request)
        except httpx.HTTPError as exc:
            logger.error("MarkLogic /v1/augment request failed: %s", exc)
            return _error_context(f"Error: MarkLogic augment request failed: {exc}")

        return Context(
            agent_id=agent_id,
            original_question_uuid=memory.original_question_uuid,
            actual_question_uuid=actual_question_uuid,
            question=question or "",
            source="augment",
            agent="augment",
            title=self.config.title,
            chunks=[Chunk(chunk_id="augment-result", text=json.dumps(response, indent=2))],
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
        context = await self.getAugment(
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
            step_title=self.step_title("Augment"),
            step_agent_path=f"/context/{self.config.id or 'augment'}",
            step_value=question,
            timeit=time() - t0,
            input_nuclia_tokens=0,
            output_nuclia_tokens=0,
            error=None,
        )
        return [missing] if missing is not None else []
