from time import time
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from nuclia_arag.agent import Agent
from nuclia_arag.configure import agent
from nuclia_arag.context.agent import ContextAgent
from nuclia_arag.context.config import ContextAgentConfig
from nuclia_arag.definition import FunctionDefinition
from nuclia_arag.manager import Manager
from nuclia_arag.memory.memory import QuestionMemory
from nuclia_arag_models.memory import Chunk, Context


class HelloWorldAgentConfig(ContextAgentConfig):
    module: Literal["hello-world"] = "hello-world"
    greeting: str = "Hello, World!"


@agent(
    id="hello-world",
    agent_type="context",
    title="Hello World",
    description="A minimal example agent that returns a fixed greeting as context.",
    config_schema=HelloWorldAgentConfig,
)
class HelloWorldAgent(ContextAgent, Agent[HelloWorldAgentConfig]):
    # Published functions called by the smart planner must be async,
    # accept memory and manager, and return a Context object.
    __published_functions__ = {
        "greet": FunctionDefinition(
            name="greet",
            description="Return a greeting string as context.",
            parameters={},
        )
    }

    async def greet(
        self,
        memory: QuestionMemory,
        manager: Manager,
        question: Optional[str] = "",
        question_uuid: Optional[str] = None,
    ) -> Context:
        return Context(
            agent_id=self.config.id or "hello-world",
            original_question_uuid=memory.original_question_uuid,
            actual_question_uuid=question_uuid or uuid4().hex,
            question=question or "",
            source="hello-world",
            agent="hello-world",
            title=self.config.title,
            chunks=[Chunk(chunk_id="greeting", text=self.config.greeting)],
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
        context = await self.greet(
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
            step_title=self.step_title("Hello World"),
            step_agent_path=f"/context/{self.config.id or 'hello-world'}",
            step_value=self.config.greeting,
            timeit=time() - t0,
            input_nuclia_tokens=0,
            output_nuclia_tokens=0,
            error=None,
        )
        return [missing] if missing is not None else []
