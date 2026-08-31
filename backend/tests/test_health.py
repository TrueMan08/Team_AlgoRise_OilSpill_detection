from fastapi.testclient import TestClient
from app.core.config import settings


def test_root_endpoint(client: TestClient) -> None:
    """Test the root endpoint returns 200 and correct structure."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["version"] == settings.VERSION
    assert data["docs"] == "/docs"
    assert data["health"] == f"{settings.API_V1_STR}/health"


def test_health_check_endpoint(client: TestClient) -> None:
    """Test the health check endpoint returns 200 and healthy status."""
    response = client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == settings.VERSION
    assert data["environment"] == settings.ENVIRONMENT
    assert "timestamp" in data


def test_ping_endpoint(client: TestClient) -> None:
    """Test the ping probe endpoint."""
    response = client.get(f"{settings.API_V1_STR}/ping")
    assert response.status_code == 200
    assert response.json() == {"ping": "pong"}


def test_openapi_docs(client: TestClient) -> None:
    """Test that OpenAPI schema is generated and accessible."""
    response = client.get(f"{settings.API_V1_STR}/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert f"{settings.API_V1_STR}/health" in data["paths"]
