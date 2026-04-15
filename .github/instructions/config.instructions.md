---
description: "Agent configuration conventions for config.yaml. Use when adding or editing workflows, context modules, or agent declarations in agents/config.yaml."
applyTo: "agents/config.yaml"
---

## config.yaml Conventions

- **`id` / `module` alignment**: The `id` field of a context entry in `config.yaml` must match both the `module` literal in the Python `*Config` class and the `id` passed to the `@agent(...)` decorator. All three must be identical strings.
- **Workflow structure**: Each workflow under `workflows:` requires `name`, `description`, `preprocess`, `context`, `generation`, and `postprocess` keys. The `context` list maps to context agent modules; `generation` uses `passthrough` unless custom generation logic is needed.
- **`prune_context`**: Set to `false` unless you explicitly want the framework to truncate context before generation. **Important**: without `prune_context: false`, `save_ctx_and_return_missing` will silently discard all context (triggering an LLM validation call that rejects non-answer-shaped text), resulting in `"(no context retrieved)"` as the final answer.
- **Workflow URL**: The workflow key in `workflows:` maps 1:1 to the `workflow_id` URL segment. Named workflows require the longer URL form: `/api/v1/agent/{agent_id}/workflow/{workflow_id}/session/{session}`. The short form `/api/v1/agent/{agent_id}/session/{session}` always uses `default` and will 404 if no `default` workflow exists.
- **Agent identity**: The top-level `drivers: []` and `rules` block apply across all workflows. Add workflow-specific constraints under the workflow's own `rules` if needed.
- **Registering a new agent**: Add an entry to the `workflows:` map and reference it by the exact `module` id used in the Python `@agent(...)` decorator. Then ensure the module is exported from `rag360_agents/__init__.py`.
