from typing import Generator
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Test client fixture providing a synchronous TestClient."""
    with TestClient(app) as test_client:
        yield test_client
