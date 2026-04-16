ARG ARAG_IMAGE=europe-west4-docker.pkg.dev/nuclia-internal/private/arag
ARG ARAG_VERSION=latest
FROM ${ARAG_IMAGE}:${ARAG_VERSION}

RUN pip install uv

ENV VIRTUAL_ENV=/app

# Copy the full data-platform workspace
COPY agents/ /app/rag360/agents/

# Install rag360 workspace packages into the existing RAO venv additively.
# uv sync is intentionally avoided here — it would remove RAO packages not in
# our lockfile. uv pip install adds without touching existing packages.
RUN uv pip install --no-sources \
    --constraints /app/rag360/agents/rao-constraints.txt \
    -e /app/rag360/agents/rag360_agents \
    watchfiles

COPY agents/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

COPY agents/config.yaml /app/rag360/config.yaml

ENV agents_config=/app/rag360/config.yaml
ENV load_modules='["rag360_agents"]'
ENV DEV=false

CMD ["/app/docker-entrypoint.sh"]
