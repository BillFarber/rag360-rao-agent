# Project Guidelines

## Architecture

This project is a **Nuclia RAO context agent** that wraps a MarkLogic REST API for RAG via MCP use cases.

Key components:

- **`agents/config.yaml`** — Declares the agent identity, workflows, and which context modules activate for each workflow. This is the source of truth for agent behaviour.
- **`agents/rag360_agents/src/rag360_agents/`** — Python package with custom context agents. Each agent subclasses `ContextAgent` and `Agent[ConfigType]` from `nuclia_arag`.
- **`agents/Dockerfile`** — Extends the `ghcr.io/nuclia/rao` base image. Installs the `rag360_agents` package additively via `uv pip install` (never `uv sync` — that would remove RAO's own packages).
- **`agents/docker-entrypoint.sh`** — Starts `arag-standalone`. When `DEV=true`, wraps it with `watchfiles` for hot-reload.
- **`agents/rao-constraints.txt`** — Pins OpenTelemetry versions to match the RAO base image. Do not upgrade these without verifying the RAO base image version.

The agent exposes port **8080**. MarkLogic is expected at `host.docker.internal:8003` (Digest Auth).

## Build and Run

```bash
# Start the full stack (dev mode — hot-reload enabled)
docker compose up

# Rebuild the image (required after Dockerfile or pyproject.toml changes)
docker compose up --build
```

Env files required at the repo root:

- **`.env.compose`** — Nuclia API key (`nua_api_key`), API URI, MarkLogic data server config. See `.env.dev.example` for the key names.
- **`.env.dev`** — Optional dev overrides (can be empty).

## Conventions

- **Adding a new context agent**: Create a new class in `agents/rag360_agents/src/rag360_agents/`, register it with `@agent(...)`, export it from `__init__.py`, then add a workflow entry in `config.yaml` referencing the module id.
- **Python changes in dev**: No rebuild needed — `agents/` is volume-mounted and `watchfiles` restarts `arag-standalone` automatically.
- **No test suite** exists yet. Manual testing is done by hitting `http://localhost:8080` after `docker compose up`.
- Prefer small atomic changes that are easy to review. For larger changes, consider breaking them into a series of smaller PRs.
