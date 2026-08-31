"""
Tests for the AIS attribution scoring engine and TOP 2 release-state selection.

Verifies:
- Hard spatial filter (>150km → excluded)
- Hard temporal filter (no AIS within ±12h → excluded)
- STRONG vessel ranks #1 with score ≥ 90
- Temporal mismatch vessel has low temporal contribution
- EvidenceScore contribution invariant: contribution == score × weight
- overall_score == sum of contributions
- TOP 2 selection: both candidates have release states and valid forward requests
- Release state: release_time_utc <= observation_time_utc (contract)
- no_strong_candidate when all scores < 0.40
- Release-state polygon-distance rule (inside window preferred)
"""

from datetime import datetime, timezone

import pytest

from app.data.ais_sample import (
    DEMO_RELEASE_WINDOW_END,
    DEMO_RELEASE_WINDOW_START,
    DEMO_SOURCE_POLYGON_RING,
)
from app.models.geometry import GeoJSONPolygon, Point
from app.models.source_candidate_region import SourceCandidateRegion
from app.models.source_region import SourceRegion
from app.services.attribution import (
    _WEIGHT_AIS_RELIABILITY,
    _WEIGHT_SPATIAL,
    _WEIGHT_TEMPORAL,
    _WEIGHT_TRAJECTORY,
    compute_ais_reliability,
    compute_spatial_score,
    compute_temporal_score,
    compute_trajectory_score,
    run_attribution,
    run_full_attribution,
    select_release_state,
    _geojson_to_shapely,
)
from app.services.vessels import get_vessels


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_demo_source_region() -> SourceRegion:
    candidate = SourceCandidateRegion(
        id="cand-demo",
        geometry=GeoJSONPolygon(
            type="Polygon",
            coordinates=[DEMO_SOURCE_POLYGON_RING],
        ),
        centroid=Point(lat=18.92, lon=72.83),
        start_time_utc=DEMO_RELEASE_WINDOW_START,
        end_time_utc=DEMO_RELEASE_WINDOW_END,
        probability=0.9,
    )
    return SourceRegion(
        id="sr-demo",
        slick_id="slick-001",
        generated_at_utc=datetime(2026, 8, 26, 23, 0, 0, tzinfo=timezone.utc),
        candidate_regions=[candidate],
    )


def _make_far_source_region() -> SourceRegion:
    """Source region far south — all vessels will fail hard filters."""
    candidate = SourceCandidateRegion(
        id="cand-far",
        geometry=GeoJSONPolygon(
            type="Polygon",
            coordinates=[[[72.81, 10.91], [72.85, 10.91], [72.85, 10.93], [72.81, 10.93], [72.81, 10.91]]],
        ),
        centroid=Point(lat=10.92, lon=72.83),
        start_time_utc=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        end_time_utc=datetime(2025, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
        probability=0.9,
    )
    return SourceRegion(
        id="sr-far",
        slick_id="slick-002",
        generated_at_utc=datetime(2025, 1, 1, 1, 0, 0, tzinfo=timezone.utc),
        candidate_regions=[candidate],
    )


def _get_demo_vessels():
    start = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    return get_vessels(bbox="70.0,17.0,74.0,21.0", start=start, end=end)


# ---------------------------------------------------------------------------
# run_attribution tests
# ---------------------------------------------------------------------------

def test_spatial_hard_filter_eliminates_distant_vessel() -> None:
    """MMSI 456789012 (~220 km away) must be excluded."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    attributions = run_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    mmsis = [a.mmsi for a in attributions]
    assert "456789012" not in mmsis


def test_strong_tanker_ranks_first() -> None:
    """MMSI 123456789 passes through source polygon in window → must rank #1 with score ≥ 90."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    attributions = run_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    assert attributions[0].mmsi == "123456789"
    assert attributions[0].overall_score >= 90.0


def test_temporal_mismatch_vessel_has_low_temporal_contribution() -> None:
    """MMSI 345678901 is 12 h before the release window — temporal contribution must be low."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    attributions = run_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    temp_attr = next(a for a in attributions if a.mmsi == "345678901")
    # Temporal score should not be 1.0 (vessel was NOT inside the release window)
    assert temp_attr.evidence_breakdown.temporal.contribution < 30.0


def test_gap_vessel_is_scored() -> None:
    """MMSI 567890123 (45-min gap) must be present in results."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    attributions = run_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    mmsis = [a.mmsi for a in attributions]
    assert "567890123" in mmsis


def test_evidence_contribution_invariant() -> None:
    """For every Attribution: contribution == score × weight (tolerance 1e-6)."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    attributions = run_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    for attr in attributions:
        bd = attr.evidence_breakdown
        for ev in [bd.spatial, bd.temporal, bd.trajectory, bd.source_probability, bd.ais_anomaly]:
            assert abs(ev.contribution - ev.score * ev.weight) < 1e-6, (
                f"MMSI {attr.mmsi}: contribution {ev.contribution} ≠ score {ev.score} × weight {ev.weight}"
            )


def test_overall_score_equals_sum_of_contributions() -> None:
    """For every Attribution: overall_score == sum of all contributions (tolerance 1e-6)."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    attributions = run_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    for attr in attributions:
        bd = attr.evidence_breakdown
        total = sum(
            ev.contribution
            for ev in [bd.spatial, bd.temporal, bd.trajectory, bd.source_probability, bd.ais_anomaly]
        )
        assert abs(attr.overall_score - total) < 1e-6, (
            f"MMSI {attr.mmsi}: overall_score {attr.overall_score} ≠ sum of contributions {total}"
        )


def test_no_strong_candidate_empty_when_far_source_region() -> None:
    """When source region is too far away, all vessels fail hard filters → empty list."""
    vessels = _get_demo_vessels()
    source_region = _make_far_source_region()

    attributions = run_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    assert len(attributions) == 0


def test_ranks_are_sequential_from_1() -> None:
    """Ranks must be 1, 2, 3, … without gaps."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    attributions = run_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    for expected_rank, attr in enumerate(attributions, start=1):
        assert attr.rank == expected_rank


# ---------------------------------------------------------------------------
# run_full_attribution / TOP 2 / release-state tests
# ---------------------------------------------------------------------------

def test_top_candidates_are_produced() -> None:
    """run_full_attribution must return exactly 2 top_candidates (given ≥2 pass filters)."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    response = run_full_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    assert len(response.top_candidates) == 2
    assert response.top_candidates[0].rank == 1
    assert response.top_candidates[1].rank == 2


def test_top_candidate_rank_1_is_strong_tanker() -> None:
    """TOP 1 must be the STRONG tanker (MMSI 123456789)."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    response = run_full_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    assert response.top_candidates[0].vessel_mmsi == "123456789"
    assert response.top_candidates[0].overall_score >= 90.0
    assert response.top_candidates[0].confidence == "High"


def test_release_state_timestamp_le_observation_time() -> None:
    """For every top candidate: release_time_utc <= observation_time_utc (contract for /forward)."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    response = run_full_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    for cand in response.top_candidates:
        assert cand.release_time_utc <= cand.observation_time_utc, (
            f"MMSI {cand.vessel_mmsi}: release {cand.release_time_utc} > observation {cand.observation_time_utc}"
        )


def test_forward_request_in_top_candidates() -> None:
    """Each top candidate must have a valid ForwardSimulationRequest."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    response = run_full_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    for cand in response.top_candidates:
        fr = cand.forward_request
        assert fr.incident_id == "inc-001"
        assert fr.vessel_mmsi == cand.vessel_mmsi
        assert fr.release_location.lat == cand.release_location.lat
        assert fr.release_location.lon == cand.release_location.lon
        assert fr.release_time_utc == cand.release_time_utc
        assert fr.observation_time_utc == cand.observation_time_utc
        # The contract: release_time_utc <= observation_time_utc
        assert fr.release_time_utc <= fr.observation_time_utc


def test_forward_request_mmsi_matches_vessel() -> None:
    """The forward_request.vessel_mmsi must match the CandidateReleaseState.vessel_mmsi."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    response = run_full_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    for cand in response.top_candidates:
        assert cand.forward_request.vessel_mmsi == cand.vessel_mmsi


def test_no_strong_candidate_flag() -> None:
    """no_strong_candidate must be True when source region is far away (all scores < 0.40)."""
    vessels = _get_demo_vessels()
    source_region = _make_far_source_region()

    response = run_full_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    assert response.no_strong_candidate is True
    assert len(response.top_candidates) == 0
    assert len(response.all_attributions) == 0


def test_release_state_uses_real_ais_coordinate() -> None:
    """Release location must exactly match one of the vessel's AIS track points."""
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()

    response = run_full_attribution(
        incident_id="inc-001",
        source_region=source_region,
        vessels=vessels,
    )

    for cand in response.top_candidates:
        vessel = next(v for v in vessels if v.mmsi == cand.vessel_mmsi)
        track_lats = {p.position.lat for p in vessel.track_points}
        track_lons = {p.position.lon for p in vessel.track_points}

        assert cand.release_location.lat in track_lats, (
            f"MMSI {cand.vessel_mmsi}: release lat {cand.release_location.lat} "
            f"not found in AIS track"
        )
        assert cand.release_location.lon in track_lons, (
            f"MMSI {cand.vessel_mmsi}: release lon {cand.release_location.lon} "
            f"not found in AIS track"
        )


def test_release_state_prefers_inside_window_for_strong_tanker() -> None:
    """
    MMSI 123456789 passes through the source polygon during the release window.
    Its release_time_utc must fall inside [window_start, window_end].
    """
    vessels = _get_demo_vessels()
    source_region = _make_demo_source_region()
    primary = source_region.candidate_regions[0]
    source_polygon = _geojson_to_shapely(primary.geometry)

    vessel = next(v for v in vessels if v.mmsi == "123456789")
    loc, release_time, obs_time, explanation = select_release_state(
        vessel, primary, source_polygon
    )

    # The strong tanker has AIS inside the release window — must prefer that
    assert primary.start_time_utc <= release_time <= primary.end_time_utc, (
        f"Expected release inside window, got {release_time}"
    )


# ---------------------------------------------------------------------------
# Unit tests for individual score functions
# ---------------------------------------------------------------------------

def test_compute_spatial_score_at_zero_distance() -> None:
    assert compute_spatial_score(0.0, 10.0) == pytest.approx(1.0)


def test_compute_spatial_score_decays() -> None:
    s10 = compute_spatial_score(10.0, 10.0)
    s20 = compute_spatial_score(20.0, 10.0)
    assert s10 > s20
    assert 0.0 < s10 < 1.0


def test_compute_temporal_score_inside_window() -> None:
    start = datetime(2026, 8, 26, 22, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 2, 0, 0, tzinfo=timezone.utc)
    ts_inside = datetime(2026, 8, 27, 0, 0, 0, tzinfo=timezone.utc)
    assert compute_temporal_score([ts_inside], start, end) == pytest.approx(1.0)


def test_compute_temporal_score_outside_window_decays() -> None:
    start = datetime(2026, 8, 26, 22, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 2, 0, 0, tzinfo=timezone.utc)
    ts_outside = datetime(2026, 8, 26, 14, 0, 0, tzinfo=timezone.utc)  # 8h before
    score = compute_temporal_score([ts_outside], start, end)
    assert 0.0 < score < 1.0


def test_compute_ais_reliability_returns_zero_with_no_window_data() -> None:
    start = datetime(2026, 8, 26, 22, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 2, 0, 0, tzinfo=timezone.utc)
    ts_outside = [datetime(2026, 8, 26, 10, 0, 0, tzinfo=timezone.utc)]
    assert compute_ais_reliability(ts_outside, start, end) == pytest.approx(0.0)


def test_weight_sum_is_one() -> None:
    """Frozen weights must sum to 1.0."""
    total = _WEIGHT_SPATIAL + _WEIGHT_TEMPORAL + _WEIGHT_TRAJECTORY + _WEIGHT_AIS_RELIABILITY
    assert abs(total - 1.0) < 1e-9
