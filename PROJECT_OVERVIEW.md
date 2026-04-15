# Project Overview: `rag360-rao-agent`

This is a **RAG (Retrieval-Augmented Generation) agent** that retrieves data from a **MarkLogic** database and exposes it to an AI assistant via the **Nuclia RAO** framework.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | [Nuclia RAO](https://nuclia.com) (`ghcr.io/nuclia/rao` base image) — `arag-standalone` server |
| Agent SDK | `nuclia_arag` Python library (`Agent`, `ContextAgent`) |
| HTTP client | `httpx` (async, Digest Auth to MarkLogic) |
| Data source | **MarkLogic** REST API |
| Language | Python 3.12+ |
| Package manager | `uv` |
| Container | Docker / Docker Compose |
| Hot reload (dev) | `watchfiles` |
| Observability | OpenTelemetry (pinned to match RAO base image) |

---

## Execution Flow

```
docker compose up
       │
       ▼
Docker builds on top of ghcr.io/nuclia/rao base image
Installs rag360_agents package via `uv pip install`
       │
       ▼
docker-entrypoint.sh
  DEV=true  → watchfiles wraps arag-standalone (auto-reload on file change)
  DEV=false → arag-standalone runs directly
       │
       ▼
arag-standalone reads:
  - config.yaml        → defines the agent, its workflow, and which modules to activate
  - load_modules env   → ["rag360_agents"] — registers RetrieveDefinitionAgent
       │
       ▼
HTTP request arrives on :8080
  → workflow: getRetrieveDefinition
  → context step: retrieve-definition module
       │
       ▼
RetrieveDefinitionAgent._get_question_context()
  → HTTP GET http://host.docker.internal:8003/v1/retrieve/definition
       (Digest Auth against MarkLogic)
  → Response text wrapped in a Context/Chunk object
       │
       ▼
generation step: passthrough (returns context directly to the caller — no LLM call)
```

The agent is essentially a **thin adapter**: it translates incoming questions into a MarkLogic API call and returns the result as RAG context for generation.

---

## How to Run

**Prerequisites:** Docker Desktop running, a MarkLogic instance accessible at `host.docker.internal:8003`.

1. **Create the env files** the compose file expects:
   ```
   .env.compose   # shared secrets (e.g. API keys for Nuclia)
   .env.dev       # dev overrides
   ```

2. **Start the stack:**
   ```bash
   docker compose up
   ```
   The agent server will be available at **http://localhost:8080**.

3. **Dev mode** is already enabled (`DEV=true` in `docker-compose.yaml`), so changes to files under `agents/` automatically restart the server via `watchfiles`. No rebuild needed for Python changes — the `agents/` directory is volume-mounted into the container.
