---
description: "Docker and container conventions for rag360. Use when editing the Dockerfile, docker-compose.yaml, docker-entrypoint.sh, or rao-constraints.txt."
applyTo: "agents/Dockerfile, docker-compose.yaml, agents/docker-entrypoint.sh, agents/rao-constraints.txt"
---

## Docker Conventions

- **`uv pip install`, never `uv sync`**: The Dockerfile installs `rag360_agents` additively into the RAO base image's existing virtualenv. Using `uv sync` would remove RAO's own packages.
- **Rebuild required**: Run `docker compose up --build` after any change to `Dockerfile`, `pyproject.toml`, or `rao-constraints.txt`. Python-only changes under `agents/` do not require a rebuild in dev (volume-mounted).
- **OpenTelemetry pins**: `rao-constraints.txt` pins OTel packages to match the RAO base image. Do not upgrade these without verifying the RAO base image version — a version mismatch breaks the Jaeger exporter.
- **Dev hot-reload**: When `DEV=true`, `docker-entrypoint.sh` wraps `arag-standalone` with `watchfiles`, watching the `/app/rag360` directory. Any file change restarts the server automatically.
- **Env files**: Two files are required at the repo root — `.env.compose` (Nuclia API key, API URI, MarkLogic data server config) and `.env.dev` (optional overrides, can be empty). See `.env.dev.example` for key names. Never commit secrets.
- **MarkLogic host**: Inside the container, MarkLogic is reachable at `host.docker.internal:8003`. This is mapped via `extra_hosts: host.docker.internal:host-gateway` in `docker-compose.yaml`.
- **Port**: The agent server is exposed on **8080**.
