import pytest
from uuid import uuid4


@pytest.fixture
def session_id() -> str:
    return uuid4().hex
