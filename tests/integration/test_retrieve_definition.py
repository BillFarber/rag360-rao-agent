"""Integration tests for the RetrieveDefinition workflow.

Requires a running docker compose stack (RAO standalone + MarkLogic).
MarkLogic credentials must be configured in .env.compose for the Docker container —
the RAO standalone strips the Authorization header before it reaches the context agent,
so credentials cannot be passed per-request; they must be in the agent config.

Run with:
    pytest tests/integration/ -m integration
"""

import httpx
import pytest

from .helpers import extract_answer


@pytest.fixture
def workflow_url(rao_base_url) -> str:
    return f"{rao_base_url}/api/v1/agent/rag360-agent/workflow/getRetrieveDefinition/session"


@pytest.mark.integration
async def test_retrieve_definition_no_credentials(workflow_url, session_id):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{workflow_url}/{session_id}",
            json={"question": "retrieve definition"},
        )

    assert response.status_code == 200
    answer = extract_answer(response.text)
    assert (
        answer is not None
    )  # some answer (error or definition) is always returned
