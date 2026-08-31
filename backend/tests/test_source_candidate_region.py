from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from app.models.geometry import GeoJSONPolygon, Point
from app.models.source_candidate_region import SourceCandidateRegion

VALID_RING = [
    [72.83, 18.92],
    [72.84, 18.92],
    [72.84, 18.93],
    [72.83, 18.93],
    [72.83, 18.92],
]


def test_valid_source_candidate_region() -> None:
    now = datetime.now(timezone.utc)
    region = SourceCandidateRegion(
        id="region-001",
        geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
        centroid=Point(lat=18.925, lon=72.835),
        start_time_utc=now,
        end_time_utc=now + timedelta(hours=6),
        probability=0.85,
    )
    assert region.id == "region-001"
    assert region.probability == 0.85
    assert region.centroid.lat == 18.925
    assert region.centroid.lon == 72.835
    assert region.geometry.type == "Polygon"


def test_source_candidate_region_equal_start_end_time() -> None:
    now = datetime.now(timezone.utc)
    region = SourceCandidateRegion(
        id="region-002",
        geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
        centroid=Point(lat=18.925, lon=72.835),
        start_time_utc=now,
        end_time_utc=now,
        probability=0.5,
    )
    assert region.start_time_utc == region.end_time_utc


def test_source_candidate_region_end_before_start_raises_error() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(
        ValidationError,
        match="end_time_utc must be greater than or equal to start_time_utc",
    ):
        SourceCandidateRegion(
            id="region-invalid-time",
            geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
            centroid=Point(lat=18.925, lon=72.835),
            start_time_utc=now,
            end_time_utc=now - timedelta(hours=1),
            probability=0.75,
        )


def test_source_candidate_region_probability_bounds() -> None:
    now = datetime.now(timezone.utc)
    base_data = {
        "id": "region-prob-check",
        "geometry": GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
        "centroid": Point(lat=18.925, lon=72.835),
        "start_time_utc": now,
        "end_time_utc": now + timedelta(hours=2),
    }

    # Probability > 1.0
    with pytest.raises(ValidationError):
        SourceCandidateRegion(**base_data, probability=1.01)

    # Probability < 0.0
    with pytest.raises(ValidationError):
        SourceCandidateRegion(**base_data, probability=-0.01)
