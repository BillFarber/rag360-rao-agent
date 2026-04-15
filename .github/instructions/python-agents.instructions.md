---
description: "Python code style and agent implementation patterns for rag360 context agents. Use when writing or reviewing agent classes, config classes, or httpx calls."
applyTo: "agents/rag360_agents/**/*.py"
---

## Python Code Style

- **Python version**: 3.12+. Use native type hints (`list[str]`, `dict[str, Any]`) — no need for `List`/`Dict` from `typing`. Use `Optional[X]` (or `X | None`) for nullable parameters.
- **Async throughout**: All agent methods are `async`. Use `httpx.AsyncClient` (not the sync client) for all HTTP calls.
- **Config via Pydantic**: Each agent has a paired `*Config` class inheriting from `ContextAgentConfig`. Config fields carry defaults; credentials come from config, never hardcoded.
- **`@agent(...)` decorator**: Required on every agent class. Must specify `id`, `agent_type`, `title`, `description`, and `config_schema`. The `id` must match the `module` literal in the config class and the `module` key in `config.yaml`.
- **`_get_question_context`**: The required entry point called by the framework. Delegate to a named business-logic method (e.g. `getRetrieveDefinition`), then call `save_ctx_and_return_missing` and `memory.add_step`. Return `[missing]` if non-`None`, else `[]`. **Note**: `save_ctx_and_return_missing` will silently discard context unless `prune_context: false` is set in `config.yaml` for this agent — without it the answer will always be `"(no context retrieved)"`.
- **`memory.add_step`**: Always record `timeit` (use `time()` before/after), set `input_nuclia_tokens=0` and `output_nuclia_tokens=0` (unless actual token counts are available), and pass `error=None` on the happy path.
- **HTTP error handling**: Catch `httpx.HTTPError` and surface a human-readable error string as the chunk text rather than raising — this keeps the agent resilient when MarkLogic is unavailable.
- **`Context` construction**: Set `agent_id` from `self.config.id` (with a fallback string), derive `actual_question_uuid` from the passed `question_uuid` or generate with `uuid4().hex`. Each chunk needs a stable `chunk_id` string.
- **MarkLogic authentication**: Always use `httpx.DigestAuth`. Credentials are read from the agent's config fields, never hardcoded.
- **Logging**: Log errors with sufficient context for debugging. Do not log sensitive information (API keys, passwords). Use appropriate log levels (`logger.error`, `logger.info`, `logger.debug`). Do not log entire MarkLogic request/response bodies — they may contain sensitive data.
