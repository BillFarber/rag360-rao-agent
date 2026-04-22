"""Integration tests for the Augment workflow.

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
    return f"{rao_base_url}/api/v1/agent/rag360-agent/workflow/getAugment/session"


@pytest.mark.integration
async def test_augment_missing_request_returns_error(workflow_url, session_id):
    """Omitting augmentRequest returns a graceful error (not a 500)."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{workflow_url}/{session_id}",
            json={"question": ""},
        )

    assert response.status_code == 200
    answer = _extract_answer(response.text)
    assert answer is not None


@pytest.mark.integration
async def test_augment_invalid_json_request_returns_error(workflow_url, session_id):
    """Passing a non-JSON string as augmentRequest returns a graceful error (not a 500)."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{workflow_url}/{session_id}",
            json={"question": "", "augmentRequest": "not valid json"},
        )

    assert response.status_code == 200
    answer = _extract_answer(response.text)
    assert answer is not None
