from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from app.models.attribution import (
    Attribution,
    EvidenceBreakdown,
    EvidenceScore,
)
from app.models.geometry import GeoJSONLineString, GeoJSONPolygon, Point
from app.models.incident import Incident
from app.models.satellite_scene import SatelliteScene
from app.models.slick import Slick
from app.models.vessel import Vessel, VesselTrackPoint

VALID_RING = [
    [72.83, 18.92],
    [72.84, 18.92],
    [72.84, 18.93],
    [72.83, 18.93],
    [72.83, 18.92],
]

FOOTPRINT_RING = [
    [72.0, 18.0],
    [73.0, 18.0],
    [73.0, 19.0],
    [72.0, 19.0],
    [72.0, 18.0],
]


def make_scene() -> SatelliteScene:
    return SatelliteScene(
        scene_id="S1A_IW_GRDH_1SDV_20260827",
        satellite="Sentinel-1A",
        sensor="C-SAR",
        sensor_type="SAR",
        acquired_at_utc=datetime(2026, 8, 27, 4, 0, 0, tzinfo=timezone.utc),
        resolution_m=10.0,
        footprint=GeoJSONPolygon(type="Polygon", coordinates=[FOOTPRINT_RING]),
        polarisation="VV+VH",
    )


def make_slick() -> Slick:
    return Slick(
        id="slick-001",
        timestamp_utc=datetime(2026, 8, 27, 4, 5, 0, tzinfo=timezone.utc),
        centroid=Point(lat=18.925, lon=72.835),
        geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
        area_km2=12.5,
        confidence=0.92,
        sensor="C-SAR",
        scene_id="S1A_IW_GRDH_1SDV_20260827",
    )


def make_vessel(mmsi: str = "123456789") -> Vessel:
    t0 = datetime(2026, 8, 27, 2, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    return Vessel(
        mmsi=mmsi,
        name="TEST VESSEL",
        track_points=[
            VesselTrackPoint(timestamp_utc=t0, position=Point(lat=18.90, lon=72.80)),
            VesselTrackPoint(timestamp_utc=t1, position=Point(lat=18.92, lon=72.83)),
        ],
        track_geometry=GeoJSONLineString(
            type="LineString",
            coordinates=[[72.80, 18.90], [72.83, 18.92]],
        ),
    )


def make_evidence_breakdown() -> EvidenceBreakdown:
    return EvidenceBreakdown(
        spatial=EvidenceScore(score=80.0, weight=0.3, contribution=24.0, explanation="Spatial"),
        temporal=EvidenceScore(score=90.0, weight=0.2, contribution=18.0, explanation="Temporal"),
        trajectory=EvidenceScore(score=70.0, weight=0.2, contribution=14.0, explanation="Trajectory"),
        source_probability=EvidenceScore(score=85.0, weight=0.15, contribution=12.75, explanation="Source"),
        ais_anomaly=EvidenceScore(score=60.0, weight=0.15, contribution=9.0, explanation="AIS"),
    )


def make_attribution(
    incident_id: str = "incident-001",
    mmsi: str = "123456789",
    rank: int = 1,
) -> Attribution:
    breakdown = make_evidence_breakdown()
    overall = (
        breakdown.spatial.contribution
        + breakdown.temporal.contribution
        + breakdown.trajectory.contribution
        + breakdown.source_probability.contribution
        + breakdown.ais_anomaly.contribution
    )
    return Attribution(
        incident_id=incident_id,
        mmsi=mmsi,
        overall_score=overall,
        rank=rank,
        evidence_breakdown=breakdown,
    )


# ==========================================
# Valid Incident Tests
# ==========================================

def test_valid_incident_minimal() -> None:
    now = datetime.now(timezone.utc)
    incident = Incident(
        id="incident-001",
        status="detected",
        detected_at_utc=now,
        updated_at_utc=now,
        scene=make_scene(),
        slick=make_slick(),
    )
    assert incident.id == "incident-001"
    assert incident.status == "detected"
    assert incident.source_region is None
    assert incident.candidate_vessels == []
    assert incident.attributions == []
    assert incident.replay is None


def test_valid_incident_with_vessels_and_attributions() -> None:
    now = datetime.now(timezone.utc)
    vessel = make_vessel()
    attribution = make_attribution(incident_id="incident-002", mmsi="123456789")

    incident = Incident(
        id="incident-002",
        status="attributed",
        detected_at_utc=now,
        updated_at_utc=now + timedelta(hours=1),
        scene=make_scene(),
        slick=make_slick(),
        candidate_vessels=[vessel],
        attributions=[attribution],
    )
    assert incident.status == "attributed"
    assert len(incident.candidate_vessels) == 1
    assert len(incident.attributions) == 1
    assert incident.attributions[0].mmsi == vessel.mmsi


def test_valid_incident_multiple_vessels_ranked() -> None:
    now = datetime.now(timezone.utc)
    vessel_a = make_vessel(mmsi="111111111")
    vessel_b = make_vessel(mmsi="222222222")
    attr_a = make_attribution(incident_id="incident-003", mmsi="111111111", rank=1)
    attr_b = make_attribution(incident_id="incident-003", mmsi="222222222", rank=2)

    incident = Incident(
        id="incident-003",
        status="analyzing",
        detected_at_utc=now,
        updated_at_utc=now,
        scene=make_scene(),
        slick=make_slick(),
        candidate_vessels=[vessel_a, vessel_b],
        attributions=[attr_a, attr_b],
    )
    assert len(incident.attributions) == 2
    assert incident.attributions[0].rank == 1
    assert incident.attributions[1].rank == 2


# ==========================================
# Validation Error Tests
# ==========================================

def test_incident_invalid_status() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Incident(
            id="incident-bad-status",
            status="unknown",
            detected_at_utc=now,
            updated_at_utc=now,
            scene=make_scene(),
            slick=make_slick(),
        )


def test_incident_updated_before_detected_raises_error() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(
        ValidationError,
        match="updated_at_utc must be greater than or equal to detected_at_utc",
    ):
        Incident(
            id="incident-bad-time",
            status="detected",
            detected_at_utc=now,
            updated_at_utc=now - timedelta(hours=1),
            scene=make_scene(),
            slick=make_slick(),
        )


def test_incident_attribution_wrong_incident_id_raises_error() -> None:
    now = datetime.now(timezone.utc)
    vessel = make_vessel()
    # Attribution references a different incident ID
    attribution = make_attribution(incident_id="other-incident", mmsi="123456789")

    with pytest.raises(
        ValidationError,
        match="All attributions must reference this incident's ID",
    ):
        Incident(
            id="incident-004",
            status="attributed",
            detected_at_utc=now,
            updated_at_utc=now,
            scene=make_scene(),
            slick=make_slick(),
            candidate_vessels=[vessel],
            attributions=[attribution],
        )


def test_incident_attribution_duplicate_ranks_raises_error() -> None:
    now = datetime.now(timezone.utc)
    vessel_a = make_vessel(mmsi="111111111")
    vessel_b = make_vessel(mmsi="222222222")
    # Both attributions have rank=1
    attr_a = make_attribution(incident_id="incident-005", mmsi="111111111", rank=1)
    attr_b = make_attribution(incident_id="incident-005", mmsi="222222222", rank=1)

    with pytest.raises(
        ValidationError,
        match="Attribution ranks must be unique within an incident",
    ):
        Incident(
            id="incident-005",
            status="attributed",
            detected_at_utc=now,
            updated_at_utc=now,
            scene=make_scene(),
            slick=make_slick(),
            candidate_vessels=[vessel_a, vessel_b],
            attributions=[attr_a, attr_b],
        )


def test_incident_attribution_mmsi_not_in_candidates_raises_error() -> None:
    now = datetime.now(timezone.utc)
    vessel = make_vessel(mmsi="111111111")
    # Attribution references a MMSI not present in candidate_vessels
    attribution = make_attribution(incident_id="incident-006", mmsi="999999999")

    with pytest.raises(
        ValidationError,
        match="does not match any candidate vessel",
    ):
        Incident(
            id="incident-006",
            status="attributed",
            detected_at_utc=now,
            updated_at_utc=now,
            scene=make_scene(),
            slick=make_slick(),
            candidate_vessels=[vessel],
            attributions=[attribution],
        )
