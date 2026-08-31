"""Tests for the counterfactual evidence comparison service.

Covers:
- Positive spatial agreement (overlapping footprint and slick)
- No-overlap case (disjoint geometries)
- Valid geometry handling
- Trajectory intersection detection
- Missing footprint fallback
- Evidence strength labels
- Schema validation
"""

from __future__ import annotations

import pytest

from app.schemas.counterfactual import CounterfactualRequest, CounterfactualResult
from app.services.counterfactual import run_counterfactual


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_slick(*, lon: float = 4.5, lat: float = 60.0, half_deg: float = 0.01):
    """Create a minimal Slick dict centred at (lon, lat)."""
    return {
        "id": "test-slick",
        "timestamp_utc": "2025-08-20T12:00:00Z",
        "centroid": {"lat": lat, "lon": lon},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lon - half_deg, lat - half_deg],
                [lon + half_deg, lat - half_deg],
                [lon + half_deg, lat + half_deg],
                [lon - half_deg, lat + half_deg],
                [lon - half_deg, lat - half_deg],
            ]],
        },
        "area_km2": 1.0,
        "confidence": 0.95,
        "sensor": "test",
        "scene_id": "test-scene",
    }


def _make_forward_result(
    *,
    footprint_lon: float = 4.5,
    footprint_lat: float = 60.0,
    footprint_half: float = 0.01,
    has_footprint: bool = True,
    traj_coords: list | None = None,
):
    """Create a minimal ForwardSimulationResult dict."""
    if traj_coords is None:
        traj_coords = [
            [footprint_lon - 0.02, footprint_lat],
            [footprint_lon, footprint_lat],
        ]

    result = {
        "incident_id": "test-001",
        "vessel_mmsi": "678901234",
        "release_location": {"lat": footprint_lat, "lon": footprint_lon - 0.02},
        "release_time_utc": "2025-08-20T10:00:00Z",
        "trajectory": {
            "type": "LineString",
            "coordinates": traj_coords,
        },
        "trajectory_timestamps_utc": [
            "2025-08-20T10:00:00Z",
            "2025-08-20T12:00:00Z",
        ][:len(traj_coords)],
        "simulation_metadata": {
            "particle_count": 1000,
            "duration_hours": 2.0,
            "oil_type": "GENERIC BUNKER C",
        },
    }

    if has_footprint:
        result["predicted_footprint"] = {
            "type": "Polygon",
            "coordinates": [[
                [footprint_lon - footprint_half, footprint_lat - footprint_half],
                [footprint_lon + footprint_half, footprint_lat - footprint_half],
                [footprint_lon + footprint_half, footprint_lat + footprint_half],
                [footprint_lon - footprint_half, footprint_lat + footprint_half],
                [footprint_lon - footprint_half, footprint_lat - footprint_half],
            ]],
        }
    else:
        result["predicted_footprint"] = None

    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCounterfactualPositiveOverlap:
    """Predicted footprint overlaps with observed slick."""

    def test_identical_geometries_perfect_agreement(self):
        """When footprint == slick, Jaccard index should be ~1.0."""
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(
                footprint_lon=4.5, footprint_lat=60.0, footprint_half=0.01,
            ),
            observed_slick=_make_slick(lon=4.5, lat=60.0, half_deg=0.01),
        )
        result = run_counterfactual(req)

        assert isinstance(result, CounterfactualResult)
        assert result.spatial_agreement > 0.95  # near-perfect overlap
        assert result.evidence_strength == "Strong"
        assert result.trajectory_reaches_slick is True
        assert result.centroid_distance_km < 0.5

    def test_partial_overlap(self):
        """Footprint partially overlaps slick."""
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(
                footprint_lon=4.505, footprint_lat=60.0, footprint_half=0.01,
            ),
            observed_slick=_make_slick(lon=4.5, lat=60.0, half_deg=0.01),
        )
        result = run_counterfactual(req)

        assert 0.0 < result.spatial_agreement < 1.0
        assert result.centroid_distance_km > 0.0


class TestCounterfactualNoOverlap:
    """Predicted footprint is far from the observed slick."""

    def test_disjoint_geometries(self):
        """Footprint and slick in different locations → zero agreement."""
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(
                footprint_lon=5.5, footprint_lat=60.5, footprint_half=0.01,
                traj_coords=[[5.48, 60.5], [5.5, 60.5]],
            ),
            observed_slick=_make_slick(lon=4.5, lat=60.0, half_deg=0.01),
        )
        result = run_counterfactual(req)

        assert result.spatial_agreement == 0.0
        assert result.evidence_strength == "None"
        assert result.trajectory_reaches_slick is False
        assert result.centroid_distance_km > 50.0


class TestCounterfactualNoFootprint:
    """Forward simulation produced no footprint."""

    def test_no_footprint_fallback(self):
        """When there is no footprint, spatial_agreement = 0."""
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(has_footprint=False),
            observed_slick=_make_slick(lon=4.5, lat=60.0, half_deg=0.01),
        )
        result = run_counterfactual(req)

        assert result.spatial_agreement == 0.0
        assert result.predicted_footprint is None
        assert result.centroid_distance_km >= 0.0
        assert "No predicted footprint" in result.explanation


class TestCounterfactualTrajectoryIntersection:
    """Trajectory reaching vs not reaching the slick."""

    def test_trajectory_reaches_slick(self):
        """Trajectory passes through the slick polygon."""
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(
                traj_coords=[[4.48, 60.0], [4.50, 60.0]],
            ),
            observed_slick=_make_slick(lon=4.5, lat=60.0, half_deg=0.01),
        )
        result = run_counterfactual(req)
        assert result.trajectory_reaches_slick is True

    def test_trajectory_misses_slick(self):
        """Trajectory is far from the slick polygon."""
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(
                traj_coords=[[5.0, 60.5], [5.1, 60.5]],
                has_footprint=False,
            ),
            observed_slick=_make_slick(lon=4.5, lat=60.0, half_deg=0.01),
        )
        result = run_counterfactual(req)
        assert result.trajectory_reaches_slick is False


class TestCounterfactualEvidenceStrength:
    """Evidence strength labels match the documented thresholds."""

    def test_strong_label(self):
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(
                footprint_lon=4.5, footprint_lat=60.0, footprint_half=0.01,
            ),
            observed_slick=_make_slick(lon=4.5, lat=60.0, half_deg=0.01),
        )
        result = run_counterfactual(req)
        assert result.evidence_strength == "Strong"

    def test_none_label(self):
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(
                footprint_lon=6.0, footprint_lat=61.0, footprint_half=0.01,
                traj_coords=[[6.0, 61.0], [6.01, 61.0]],
            ),
            observed_slick=_make_slick(lon=4.5, lat=60.0, half_deg=0.01),
        )
        result = run_counterfactual(req)
        assert result.evidence_strength == "None"


class TestCounterfactualSchemaValidation:
    """Schema-level validation for CounterfactualRequest."""

    def test_valid_request_parses(self):
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(),
            observed_slick=_make_slick(),
        )
        assert req.incident_id == "test-001"
        assert req.vessel_mmsi == "678901234"

    def test_invalid_mmsi_rejected(self):
        with pytest.raises(Exception):
            CounterfactualRequest(
                incident_id="test-001",
                vessel_mmsi="123",  # too short
                forward_result=_make_forward_result(),
                observed_slick=_make_slick(),
            )


class TestCounterfactualExplanation:
    """The explanation field contains useful information."""

    def test_explanation_mentions_jaccard(self):
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(),
            observed_slick=_make_slick(),
        )
        result = run_counterfactual(req)
        assert "Jaccard" in result.explanation or "overlap" in result.explanation
        assert "NOT proof of responsibility" in result.explanation

    def test_explanation_mentions_centroid_distance(self):
        req = CounterfactualRequest(
            incident_id="test-001",
            vessel_mmsi="678901234",
            forward_result=_make_forward_result(),
            observed_slick=_make_slick(),
        )
        result = run_counterfactual(req)
        assert "Centroid distance" in result.explanation
