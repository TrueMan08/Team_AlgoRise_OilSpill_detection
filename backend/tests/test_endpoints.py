from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.geometry import GeoJSONPolygon, Point
from app.models.slick import Slick

SAMPLE_SLICK = Slick(
    id="slick-001",
    timestamp_utc=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
    centroid=Point(lat=18.92, lon=72.83),
    geometry=GeoJSONPolygon(
        type="Polygon",
        coordinates=[
            [
                [72.83, 18.92],
                [72.84, 18.92],
                [72.84, 18.93],
                [72.83, 18.93],
                [72.83, 18.92],
            ]
        ],
    ),
    area_km2=10.5,
    confidence=0.95,
)


def test_detect_endpoint(client: TestClient) -> None:
    # /detect now returns a LIST of slicks (a scene can contain several);
    # the service function is async, so patch with an AsyncMock.
    with patch(
        "app.api.v1.endpoints.detection.detect_oil_spill",
        new=AsyncMock(return_value=[SAMPLE_SLICK]),
    ):
        files = {"image": ("sentinel_scene.tif", b"mock_satellite_image_bytes", "image/tiff")}
        response = client.post(f"{settings.API_V1_STR}/detect", files=files)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["id"] == "slick-001"
        assert data[0]["area_km2"] == 10.5
        assert data[0]["confidence"] == 0.95


def test_hindcast_endpoint(client: TestClient) -> None:
    # The endpoint now requires a HindcastRequest JSON body.
    # A request with no body should be rejected with 422.
    response = client.post(f"{settings.API_V1_STR}/hindcast")
    assert response.status_code == 422


def test_vessels_endpoint(client: TestClient) -> None:
    # GET /vessels now requires bbox, start, end query params.
    # A call with valid params should return 200 with an AIS vessel list.
    response = client.get(
        f"{settings.API_V1_STR}/vessels",
        params={
            "bbox": "71.0,18.0,73.5,19.5",
            "start": "2026-08-26T00:00:00Z",
            "end": "2026-08-27T12:00:00Z",
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Should return a list (may be empty if AIS data not in bbox)
    assert isinstance(data, list)


def test_attribute_endpoint(client: TestClient) -> None:
    # POST /attribute now requires an AttributeRequest JSON body.
    # A request with no body should be rejected with 422.
    response = client.post(f"{settings.API_V1_STR}/attribute")
    assert response.status_code == 422


def test_replay_endpoint(client: TestClient) -> None:
    # the cached demo incident returns a full Replay; unknown ids 404
    response = client.get(f"{settings.API_V1_STR}/replay/incident-demo-001")
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "incident-demo-001"
    assert len(data["frames"]) >= 2

    missing = client.get(f"{settings.API_V1_STR}/replay/incident-nope")
    assert missing.status_code == 404
