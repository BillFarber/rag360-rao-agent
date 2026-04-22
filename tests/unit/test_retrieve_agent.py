"""Unit tests for RetrieveAgent.getRetrieve."""

import json
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from rao_agent.memory import QuestionMemory

from rag360_agents.retrieve_agent import RetrieveAgent, RetrieveAgentConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

BASE64_ADMIN = "YWRtaW46YWRtaW4="  # admin:admin


def _make_memory(retrieve_query: str | None = None, auth_header: str | None = None) -> QuestionMemory:
    memory = QuestionMemory()
    if retrieve_query is not None:
        memory.arguments = {"retrieveQuery": retrieve_query}
    if auth_header is not None:
        memory.headers = {"Authorization": auth_header}
    return memory


def _make_agent(auth_method: str = "digest") -> RetrieveAgent:
    mock = Mock(spec=RetrieveAgent)
    mock.config = RetrieveAgentConfig(auth_method=auth_method)
    mock.getRetrieve = RetrieveAgent.getRetrieve.__get__(mock)
    return mock


def _chunk_text(context) -> str:
    return context.chunks[0].text


# ── Missing / invalid retrieveQuery ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_retrieve_query_returns_error():
    agent = _make_agent()
    memory = _make_memory()  # no retrieveQuery
    ctx = await agent.getRetrieve(memory=memory, manager=Mock())
    assert "retrieveQuery parameter is required" in _chunk_text(ctx)
    assert ctx.chunks[0].chunk_id == "retrieve-error"


@pytest.mark.asyncio
async def test_invalid_json_returns_error():
    agent = _make_agent()
    memory = _make_memory(retrieve_query="not valid json")
    ctx = await agent.getRetrieve(memory=memory, manager=Mock())
    assert "valid JSON string" in _chunk_text(ctx)
    assert ctx.chunks[0].chunk_id == "retrieve-error"


@pytest.mark.asyncio
async def test_non_object_json_is_accepted():
    """A JSON array is technically valid JSON — retrieve_raw will receive it."""
    agent = _make_agent("api_key")
    memory = _make_memory(retrieve_query='["item1"]')
    ml_response = {"matches": []}
    with patch(
        "rag360_agents.retrieve_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.retrieve_raw.return_value = ml_response
        mock_build.return_value = (mock_conn, None)
        ctx = await agent.getRetrieve(memory=memory, manager=Mock())
    assert ctx.chunks[0].chunk_id == "retrieve-result"


# ── Auth errors ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_auth_header_returns_error():
    agent = _make_agent("digest")
    memory = _make_memory(retrieve_query='{"text": "diabetes"}')
    ctx = await agent.getRetrieve(memory=memory, manager=Mock())
    assert "Error:" in _chunk_text(ctx)
    assert ctx.chunks[0].chunk_id == "retrieve-error"


# ── Successful retrieval ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_retrieval_returns_result_chunk():
    agent = _make_agent("api_key")
    memory = _make_memory(retrieve_query='{"text": "diabetes OR insulin"}')
    ml_response = {"matches": [{"id": "doc1", "score": 0.9}]}
    with patch(
        "rag360_agents.retrieve_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.retrieve_raw.return_value = ml_response
        mock_build.return_value = (mock_conn, None)
        ctx = await agent.getRetrieve(memory=memory, manager=Mock())
    assert ctx.chunks[0].chunk_id == "retrieve-result"
    result = json.loads(_chunk_text(ctx))
    assert result["matches"][0]["id"] == "doc1"


@pytest.mark.asyncio
async def test_retrieve_raw_called_with_parsed_query():
    """The dict parsed from retrieveQuery is forwarded verbatim to retrieve_raw."""
    agent = _make_agent("api_key")
    query_dict = {"text": "diabetes OR insulin", "topk": 5}
    memory = _make_memory(retrieve_query=json.dumps(query_dict))
    with patch(
        "rag360_agents.retrieve_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.retrieve_raw.return_value = {}
        mock_build.return_value = (mock_conn, None)
        await agent.getRetrieve(memory=memory, manager=Mock())
    mock_conn.retrieve_raw.assert_called_once_with(query_dict)


@pytest.mark.asyncio
async def test_digest_auth_credentials_forwarded():
    """With digest auth, credentials from the Authorization header reach MarkLogic."""
    agent = _make_agent("digest")
    memory = _make_memory(
        retrieve_query='{"text": "test"}',
        auth_header=f"Bearer {BASE64_ADMIN}",
    )
    with patch(
        "rag360_agents.retrieve_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.retrieve_raw.return_value = {}
        mock_build.return_value = (mock_conn, None)
        ctx = await agent.getRetrieve(memory=memory, manager=Mock())
    assert ctx.chunks[0].chunk_id == "retrieve-result"
    _, kwargs = mock_build.call_args
    assert kwargs["auth_method"] == "digest"
    assert kwargs["headers"]["Authorization"] == f"Bearer {BASE64_ADMIN}"


# ── HTTP errors ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_error_from_marklogic_returns_error_context():
    agent = _make_agent("api_key")
    memory = _make_memory(retrieve_query='{"text": "diabetes"}')
    with patch(
        "rag360_agents.retrieve_agent.build_marklogic_connection_from_headers"
    ) as mock_build:
        mock_conn = AsyncMock()
        mock_conn.retrieve_raw.side_effect = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=Mock(),
            response=Mock(status_code=503),
        )
        mock_build.return_value = (mock_conn, None)
        ctx = await agent.getRetrieve(memory=memory, manager=Mock())
    assert "retrieve request failed" in _chunk_text(ctx)
    assert ctx.chunks[0].chunk_id == "retrieve-error"
