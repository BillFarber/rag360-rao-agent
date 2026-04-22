"""Unit tests for AugmentAgent.getAugment."""

import json
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from rao_agent.memory import QuestionMemory

from rag360_agents.augment_agent import AugmentAgent, AugmentAgentConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

BASE64_ADMIN = "YWRtaW46YWRtaW4="  # admin:admin


def _make_memory(augment_request: str | None = None, auth_header: str | None = None) -> QuestionMemory:
    memory = QuestionMemory()
    if augment_request is not None:
        memory.arguments = {"augmentRequest": augment_request}
    if auth_header is not None:
        memory.headers = {"Authorization": auth_header}
    return memory


def _make_agent(auth_method: str = "digest") -> AugmentAgent:
    mock = Mock(spec=AugmentAgent)
    mock.config = AugmentAgentConfig(auth_method=auth_method)
    mock.getAugment = AugmentAgent.getAugment.__get__(mock)
    return mock


def _chunk_text(context) -> str:
    return context.chunks[0].text


# ── Missing / invalid augmentRequest ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_augment_request_returns_error():
    agent = _make_agent()
    memory = _make_memory()  # no augmentRequest
    ctx = await agent.getAugment(memory=memory, manager=Mock())
    assert "augmentRequest parameter is required" in _chunk_text(ctx)
    assert ctx.chunks[0].chunk_id == "augment-error"


@pytest.mark.asyncio
async def test_invalid_json_returns_error():
    agent = _make_agent()
    memory = _make_memory(augment_request="not valid json")
    ctx = await agent.getAugment(memory=memory, manager=Mock())
    assert "valid JSON string" in _chunk_text(ctx)
    assert ctx.chunks[0].chunk_id == "augment-error"


@pytest.mark.asyncio
async def test_non_object_json_is_accepted():
    """A JSON array is technically valid JSON — augment_raw will receive it."""
    agent = _make_agent("api_key")
    memory = _make_memory(augment_request='["/doc1.json"]')
    ml_response = {"documents": []}
    with patch(
        "rag360_agents.augment_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.augment_raw.return_value = ml_response
        mock_build.return_value = (mock_conn, None)
        ctx = await agent.getAugment(memory=memory, manager=Mock())
    assert ctx.chunks[0].chunk_id == "augment-result"


# ── Auth errors ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_auth_header_returns_error():
    agent = _make_agent("digest")
    memory = _make_memory(augment_request='{"URIs": ["/doc1.json"]}')
    # no Authorization header → build_marklogic_connection_from_headers returns error
    ctx = await agent.getAugment(memory=memory, manager=Mock())
    assert "Error:" in _chunk_text(ctx)
    assert ctx.chunks[0].chunk_id == "augment-error"


# ── Successful augment ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_augment_returns_result_chunk():
    agent = _make_agent("api_key")
    memory = _make_memory(augment_request='{"URIs": ["/documents/doc1.json"]}')
    ml_response = {"documents": [{"uri": "/documents/doc1.json", "content": "some text"}]}
    with patch(
        "rag360_agents.augment_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.augment_raw.return_value = ml_response
        mock_build.return_value = (mock_conn, None)
        ctx = await agent.getAugment(memory=memory, manager=Mock())
    assert ctx.chunks[0].chunk_id == "augment-result"
    result = json.loads(_chunk_text(ctx))
    assert result["documents"][0]["uri"] == "/documents/doc1.json"


@pytest.mark.asyncio
async def test_augment_raw_called_with_parsed_request():
    """The dict parsed from augmentRequest is forwarded verbatim to augment_raw."""
    agent = _make_agent("api_key")
    request_dict = {"URIs": ["/documents/doc1.json", "/documents/doc2.json"]}
    memory = _make_memory(augment_request=json.dumps(request_dict))
    with patch(
        "rag360_agents.augment_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.augment_raw.return_value = {}
        mock_build.return_value = (mock_conn, None)
        await agent.getAugment(memory=memory, manager=Mock())
    mock_conn.augment_raw.assert_called_once_with(request_dict)


@pytest.mark.asyncio
async def test_lowercase_uris_key_is_normalized():
    """LLM clients often send 'uris' (lowercase) — agent should normalize to 'URIs'."""
    agent = _make_agent("api_key")
    memory = _make_memory(augment_request='{"uris": ["/doc1.json"]}')
    with patch(
        "rag360_agents.augment_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.augment_raw.return_value = {}
        mock_build.return_value = (mock_conn, None)
        await agent.getAugment(memory=memory, manager=Mock())
    mock_conn.augment_raw.assert_called_once_with({"URIs": ["/doc1.json"]})


@pytest.mark.asyncio
async def test_digest_auth_credentials_forwarded():
    """With digest auth, credentials from the Authorization header reach MarkLogic."""
    agent = _make_agent("digest")
    memory = _make_memory(
        augment_request='{"URIs": ["/doc1.json"]}',
        auth_header=f"Bearer {BASE64_ADMIN}",
    )
    with patch(
        "rag360_agents.augment_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.augment_raw.return_value = {}
        mock_build.return_value = (mock_conn, None)
        ctx = await agent.getAugment(memory=memory, manager=Mock())
    assert ctx.chunks[0].chunk_id == "augment-result"
    _, kwargs = mock_build.call_args
    assert kwargs["auth_method"] == "digest"
    assert kwargs["headers"]["Authorization"] == f"Bearer {BASE64_ADMIN}"


# ── HTTP errors ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_error_from_marklogic_returns_error_context():
    agent = _make_agent("api_key")
    memory = _make_memory(augment_request='{"URIs": ["/doc1.json"]}')
    with patch(
        "rag360_agents.augment_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.augment_raw.side_effect = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=Mock(),
            response=Mock(status_code=503),
        )
        mock_build.return_value = (mock_conn, None)
        ctx = await agent.getAugment(memory=memory, manager=Mock())
    assert "augment request failed" in _chunk_text(ctx)
    assert ctx.chunks[0].chunk_id == "augment-error"
