from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.geometry import GeoJSONPoint, GeoJSONPolygon, Point
from app.models.attribution import SourceRegionMatch
from app.models.incident import Incident
from app.models.replay_frame import ReplayFrame, ReplayVesselState
from app.models.satellite_scene import SatelliteScene
from app.models.slick import Slick
from app.models.vessel import Vessel, VesselTrackPoint


RING = [
    [72.83, 18.92],
    [72.84, 18.92],
    [72.84, 18.93],
    [72.83, 18.93],
    [72.83, 18.92],
]


def test_utc_timestamps_are_normalized() -> None:
    scene = SatelliteScene(
        scene_id="scene-1",
        satellite="Sentinel-1A",
        sensor="C-SAR",
        sensor_type="SAR",
        acquired_at_utc=datetime(2026, 8, 27, 9, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        resolution_m=10,
        footprint=GeoJSONPolygon(type="Polygon", coordinates=[RING]),
    )
    assert scene.acquired_at_utc.tzinfo == timezone.utc
    assert scene.acquired_at_utc.hour == 3
    assert scene.acquired_at_utc.minute == 30


def test_naive_utc_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Slick(
            id="slick-1",
            timestamp_utc=datetime(2026, 8, 27, 4),
            centroid=Point(lat=18.92, lon=72.83),
            geometry=GeoJSONPolygon(type="Polygon", coordinates=[RING]),
            area_km2=1,
            confidence=0.9,
        )


def test_replay_frame_rejects_duplicate_vessel_mmsis() -> None:
    position = GeoJSONPoint(type="Point", coordinates=[72.83, 18.92])
    vessel = ReplayVesselState(
        mmsi="123456789",
        position=position,
        position_source="observed",
    )
    with pytest.raises(ValidationError, match="duplicate vessel MMSIs"):
        ReplayFrame(
            timestamp_utc=datetime(2026, 8, 27, 4, tzinfo=timezone.utc),
            vessels=[vessel, vessel],
        )


def test_attribution_rejects_duplicate_source_region_matches() -> None:
    from app.models.attribution import Attribution, EvidenceBreakdown, EvidenceScore

    def score(value: float, weight: float) -> EvidenceScore:
        return EvidenceScore(
            score=value,
            weight=weight,
            contribution=value * weight,
            explanation="test",
        )

    breakdown = EvidenceBreakdown(
        spatial=score(80, 0.3),
        temporal=score(80, 0.2),
        trajectory=score(80, 0.2),
        source_probability=score(80, 0.15),
        ais_anomaly=score(80, 0.15),
    )
    with pytest.raises(ValidationError, match="same source region twice"):
        Attribution(
            incident_id="incident-1",
            mmsi="123456789",
            overall_score=80,
            rank=1,
            evidence_breakdown=breakdown,
            matched_source_regions=[
                SourceRegionMatch(source_candidate_region_id="src-1", compatibility_score=0.5),
                SourceRegionMatch(source_candidate_region_id="src-1", compatibility_score=0.4),
            ],
        )


def test_vessel_requires_two_track_points() -> None:
    with pytest.raises(ValidationError):
        Vessel(
            mmsi="123456789",
            track_points=[
                VesselTrackPoint(
                    timestamp_utc=datetime(2026, 8, 27, 4, tzinfo=timezone.utc),
                    position=Point(lat=18.92, lon=72.83),
                )
            ],
            track_geometry={
                "type": "LineString",
                "coordinates": [[72.83, 18.92], [72.84, 18.93]],
            },
        )


def test_incident_rejects_mismatched_slick_scene_reference() -> None:
    timestamp = datetime(2026, 8, 27, 4, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="slick.scene_id"):
        Incident(
            id="incident-1",
            status="detected",
            detected_at_utc=timestamp,
            updated_at_utc=timestamp,
            scene=SatelliteScene(
                scene_id="scene-1",
                satellite="Sentinel-1A",
                sensor="C-SAR",
                sensor_type="SAR",
                acquired_at_utc=timestamp,
                resolution_m=10,
                footprint=GeoJSONPolygon(type="Polygon", coordinates=[RING]),
            ),
            slick=Slick(
                id="slick-1",
                timestamp_utc=timestamp,
                centroid=Point(lat=18.92, lon=72.83),
                geometry=GeoJSONPolygon(type="Polygon", coordinates=[RING]),
                area_km2=1,
                confidence=0.9,
                scene_id="different-scene",
            ),
        )
