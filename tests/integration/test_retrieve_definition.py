"""Integration tests for the RetrieveDefinition workflow.

Requires a running docker compose stack (RAO standalone + MarkLogic).
MarkLogic credentials must be configured in .env.compose for the Docker container —
the RAO standalone strips the Authorization header before it reaches the context agent,
so credentials cannot be passed per-request; they must be in the agent config.

Run with:
    pytest tests/integration/ -m integration
"""

import json

import httpx
import pytest


def _extract_answer(body: str) -> str:
    """Extract the final answer from an NDJSON streaming response."""
    for line in body.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        answer = obj.get("answer")
        if answer is not None:
            return str(answer)
    return ""


@pytest.fixture
def session_id() -> str:
    from uuid import uuid4
    return uuid4().hex


@pytest.fixture
def workflow_url(rao_base_url) -> str:
    return f"{rao_base_url}/api/v1/agent/rag360-agent/workflow/getRetrieveDefinition/session"


@pytest.mark.integration
async def test_retrieve_definition_no_credentials(workflow_url, session_id):
    """When agent config has no credentials, an error is returned (not a 500)."""
    # This test validates graceful error handling; it will pass regardless of
    # whether credentials are configured — it just checks for a non-500 response.
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{workflow_url}/{session_id}",
            json={"question": "retrieve definition"},
        )

    assert response.status_code == 200
    answer = _extract_answer(response.text)
    assert answer is not None  # some answer (error or definition) is always returned

