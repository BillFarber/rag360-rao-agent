import base64
import os

import pytest


@pytest.fixture
def rao_base_url() -> str:
    return os.environ.get("RAO_BASE_URL", "http://localhost:8080")


@pytest.fixture
def marklogic_username() -> str:
    return os.environ.get("MARKLOGIC_USERNAME", "admin")


@pytest.fixture
def marklogic_password() -> str:
    return os.environ.get("MARKLOGIC_PASSWORD", "admin")


@pytest.fixture
def digest_bearer_header(marklogic_username, marklogic_password) -> dict:
    """Authorization header with base64-encoded username:password for digest/basic auth."""
    token = base64.b64encode(
        f"{marklogic_username}:{marklogic_password}".encode()
    ).decode()
    return {"Authorization": f"Bearer {token}"}
