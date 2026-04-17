"""Unit tests for build_marklogic_connection_from_headers."""

import base64

import pytest

from rag360_agents.driver import MarkLogicConnection, build_marklogic_connection_from_headers

DUMMY_URL = "http://localhost:8003"


def _call(headers: dict, auth_method: str = "digest"):
    return build_marklogic_connection_from_headers(
        headers=headers,
        auth_method=auth_method,
        marklogic_url=DUMMY_URL,
    )


def _bearer(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Bearer {token}"}


# ── JWT ──────────────────────────────────────────────────────────────────────


def test_jwt_with_bearer_header():
    conn, err = _call({"Authorization": "Bearer my.jwt.token"}, "jwt")
    assert err is None
    assert isinstance(conn, MarkLogicConnection)


def test_jwt_missing_bearer_header():
    conn, err = _call({}, "jwt")
    assert conn is None
    assert err is not None
    assert "Authorization Bearer token is required" in err


# ── Digest ────────────────────────────────────────────────────────────────────


def test_digest_with_valid_base64_bearer():
    conn, err = _call(_bearer("testuser", "testpass"), "digest")
    assert err is None
    assert isinstance(conn, MarkLogicConnection)


def test_digest_with_invalid_base64_bearer():
    conn, err = _call({"Authorization": "Bearer !!not-valid-base64!!"}, "digest")
    assert conn is None
    assert err is not None
    assert "could not be decoded" in err


def test_digest_missing_bearer_header():
    conn, err = _call({}, "digest")
    assert conn is None
    assert err is not None
    assert "digest" in err.lower()


# ── Basic ─────────────────────────────────────────────────────────────────────


def test_basic_with_valid_base64_bearer():
    conn, err = _call(_bearer("testuser", "testpass"), "basic")
    assert err is None
    assert isinstance(conn, MarkLogicConnection)


def test_basic_missing_bearer_header():
    conn, err = _call({}, "basic")
    assert conn is None
    assert err is not None
    assert "basic" in err.lower()


# ── API key ───────────────────────────────────────────────────────────────────


def test_api_key_no_bearer_needed():
    conn, err = _call({}, "api_key")
    assert err is None
    assert isinstance(conn, MarkLogicConnection)


# ── Header key case-insensitivity ─────────────────────────────────────────────


def test_case_insensitive_authorization_key():
    token = base64.b64encode(b"testuser:testpass").decode()
    conn, err = _call({"authorization": f"Bearer {token}"}, "digest")
    assert err is None
    assert isinstance(conn, MarkLogicConnection)
