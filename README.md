# rag360-rao-agent

A **Retrieval-Augmented Generation (RAG) context agent** built on the [Nuclia RAO](https://nuclia.com) framework. It wraps a MarkLogic REST API to provide structured retrieval context for AI assistants via MCP use cases.

## Overview

The agent acts as a thin adapter: it translates incoming requests into MarkLogic API calls and returns the results as RAG context for downstream generation. The generation step uses `passthrough` — no additional LLM call is made; the retrieved context is returned directly to the caller.

## Architecture

```
  Client (HTTP)
       │
       ▼ :8080
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                     │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │              arag-standalone                     │   │
│  │            (Nuclia RAO server)                   │   │
│  │                                                  │   │
│  │  config.yaml ──► workflows:                      │   │
│  │                                                  │   │
│  │  getRetrieveDefinition  getRetrieve  getAugment  │   │
│  │          │                  │            │       │   │
│  │          ▼                  ▼            ▼       │   │
│  │  RetrieveDefinition   Retrieve       Augment     │   │
│  │  Agent                Agent          Agent       │   │
│  │  GET /v1/retrieve/    POST /v1/      POST /v1/   │   │
│  │    definition         retrieve       augment     │   │
│  │          │                  │            │       │   │
│  │          └──────────┬───────┘────────────┘       │   │
│  │                     ▼                            │   │
│  │          generation: passthrough                 │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Base image: ghcr.io/nuclia/rao                         │
│  Package:    rag360_agents (uv pip install)             │
└─────────────────────────────────────────────────────────┘
       │
       ▼ HTTP (Digest / Basic / JWT Auth)
┌──────────────────────┐
│      MarkLogic       │
│  host.docker.        │
│  internal:8003       │
└──────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | Nuclia RAO (`ghcr.io/nuclia/rao`) — `arag-standalone` server |
| Agent SDK | `nuclia_arag` Python library (`Agent`, `ContextAgent`) |
| HTTP client | `httpx` (async) |
| Data source | MarkLogic REST API |
| Authentication | Digest, Basic, or JWT (configurable) |
| Language | Python 3.12+ |
| Package manager | `uv` |
| Container | Docker / Docker Compose |
| Hot reload (dev) | `watchfiles` |
| Observability | OpenTelemetry (pinned to match RAO base image) |

## Project Structure

```
rag360-rao-agent/
├── agents/
│   ├── config.yaml                   # Agent identity, workflows, and module bindings
│   ├── Dockerfile                    # Extends ghcr.io/nuclia/rao base image
│   ├── docker-entrypoint.sh          # Starts arag-standalone (with watchfiles in dev)
│   ├── rao-constraints.txt           # Pinned OpenTelemetry versions
│   └── rag360_agents/
│       └── src/rag360_agents/
│           ├── __init__.py
│           ├── driver.py                       # MarkLogicConnection + shared auth helper
│           ├── retrieve_definition_agent.py    # RetrieveDefinitionAgent (GET /v1/retrieve/definition)
│           ├── retrieve_agent.py               # RetrieveAgent (POST /v1/retrieve passthrough)
│           └── augment_agent.py                # AugmentAgent (POST /v1/augment passthrough)
├── docker-compose.yaml
├── pyproject.toml
└── .env.compose.example              # Required env var names
```

## Getting Started

### Prerequisites

- Docker Desktop running
- A MarkLogic instance accessible at `host.docker.internal:8003`
- A Nuclia API key

### 1. Configure environment files

Copy `.env.compose.example` and populate the required values:

```bash
# .env.compose — required (untracked; copy from .env.compose.example)
nua_api_key=<your-nua-api-key>
nua_api_uri=https://aws-us-east-2-1.rag.progress.cloud

# .env.dev — optional overrides (can be empty)
```

### 2. Start the stack

```bash
docker compose up
```

The agent server will be available at **http://localhost:8080**.

For changes that require a rebuild (e.g. `Dockerfile`, `pyproject.toml`):

```bash
docker compose up --build
```

### 3. Dev mode

`DEV=true` is set by default in `docker-compose.yaml`. The `agents/` directory is volume-mounted into the container, and `watchfiles` restarts `arag-standalone` automatically on any file change. **No rebuild is needed for Python-only changes.**

## Authentication

MarkLogic credentials are **not** stored in config — they are forwarded per-request via the `Authorization` header using base64-encoded `username:password`:

```
Authorization: Bearer <base64(username:password)>
```

The agent supports three `auth_method` modes (configured in each agent's `*Config` class):

| Mode | Credential source |
|---|---|
| `digest` (default) | Base64 `username:password` in `Authorization: Bearer` header |
| `basic` | Same as digest, but uses HTTP Basic Auth + TLS |
| `jwt` | Raw JWT token in `Authorization: Bearer` header |

## API Usage

The agent exposes three Nuclia RAO workflow endpoints:

**Retrieve Definition** — fetch available labels and filters schema:
```
POST /api/v1/agent/rag360-agent/workflow/getRetrieveDefinition/session/{session_id}
Authorization: Bearer <base64(marklogic-user:marklogic-password)>
Content-Type: application/json

{"question": ""}
```

**Retrieve** — post a query body directly to MarkLogic and return the raw response:
```
POST /api/v1/agent/rag360-agent/workflow/getRetrieve/session/{session_id}
Authorization: Bearer <base64(marklogic-user:marklogic-password)>
Content-Type: application/json

{
  "question": "",
  "retrieveQuery": "{\"text\": \"What is X?\", \"topk\": 10}"
}
```

The `retrieveQuery` string is parsed as JSON and posted as-is as the body to `/v1/retrieve`.

**Augment** — fetch full document content from MarkLogic by URI:
```
POST /api/v1/agent/rag360-agent/workflow/getAugment/session/{session_id}
Authorization: Bearer <base64(marklogic-user:marklogic-password)>
Content-Type: application/json

{
  "question": "",
  "augmentRequest": "{\"URIs\": [\"/medical/doc001.json\"]}"
}
```

The `augmentRequest` string is parsed as JSON and posted as-is as the body to `/v1/augment`.

All workflows use the `passthrough` generation step — no additional LLM call is made; retrieved context is returned directly to the caller.

## Adding a New Context Agent

1. Create a new class in `agents/rag360_agents/src/rag360_agents/` subclassing `ContextAgent` and `Agent[ConfigType]`.
2. Decorate it with `@agent(id=..., agent_type="context", ...)`. The `id` must match the `module` literal in the paired `*Config` class.
3. Use `build_marklogic_connection_from_headers` from `driver.py` for MarkLogic auth — do not copy the auth logic.
4. Access workflow call arguments via `memory.arguments` (a dict), not `extra_context`.
5. Export it from `__init__.py`.
6. Add a new workflow entry in `agents/config.yaml` referencing the module id. Set `prune_context: false` to avoid silent context discard.

## Key Constraints

- **`uv pip install`, never `uv sync`**: The Dockerfile installs packages additively into the RAO base image's virtualenv. `uv sync` would remove RAO's own packages.
- **OpenTelemetry pins**: `rao-constraints.txt` pins OTel packages to match the RAO base image. Do not upgrade without verifying compatibility.
- **`prune_context: false`**: Required in `config.yaml` for each context module; without it, all retrieved context is silently discarded and the answer will always be `"(no context retrieved)"`.
