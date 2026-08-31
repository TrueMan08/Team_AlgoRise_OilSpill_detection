from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from app.models.geometry import GeoJSONPolygon, Point
from app.models.source_candidate_region import SourceCandidateRegion
from app.models.source_region import SourceRegion

VALID_RING = [
    [72.83, 18.92],
    [72.84, 18.92],
    [72.84, 18.93],
    [72.83, 18.93],
    [72.83, 18.92],
]


def test_valid_source_region() -> None:
    now = datetime.now(timezone.utc)
    candidates = [
        SourceCandidateRegion(
            id="cand-1",
            geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
            centroid=Point(lat=18.92, lon=72.83),
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            probability=0.7,
        ),
        SourceCandidateRegion(
            id="cand-2",
            geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
            centroid=Point(lat=18.94, lon=72.85),
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=3),
            probability=0.3,
        ),
    ]

    source_region = SourceRegion(
        id="sr-001",
        slick_id="slick-001",
        candidate_regions=candidates,
        generated_at_utc=now,
    )
    assert source_region.id == "sr-001"
    assert source_region.slick_id == "slick-001"
    assert len(source_region.candidate_regions) == 2


def test_source_region_duplicate_candidate_ids_raises_error() -> None:
    now = datetime.now(timezone.utc)
    candidates = [
        SourceCandidateRegion(
            id="cand-duplicate",
            geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
            centroid=Point(lat=18.92, lon=72.83),
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            probability=0.7,
        ),
        SourceCandidateRegion(
            id="cand-duplicate",  # Duplicate ID
            geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
            centroid=Point(lat=18.94, lon=72.85),
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=3),
            probability=0.3,
        ),
    ]

    with pytest.raises(
        ValidationError,
        match="Candidate region IDs must be unique within a SourceRegion",
    ):
        SourceRegion(
            id="sr-002",
            slick_id="slick-001",
            candidate_regions=candidates,
            generated_at_utc=now,
        )


def test_source_region_empty_candidates_raises_error() -> None:
    with pytest.raises(ValidationError):
        SourceRegion(
            id="sr-003",
            slick_id="slick-001",
            candidate_regions=[],
            generated_at_utc=datetime.now(timezone.utc),
        )
