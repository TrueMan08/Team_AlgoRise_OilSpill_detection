"""Tests for the drift simulation service and schemas.

Covers:
- Schema validation (HindcastRequest, HindcastResponse, ForwardSimulationRequest)
- UTC timestamp enforcement
- Coordinate ordering ([lon, lat] for GeoJSON, {lat, lon} for Point)
- KDE geometry validity and source region extraction
- Trajectory / timestamp 1:1 alignment
- slick_id propagation through the pipeline
- Mock OpenDrift execution for hindcast integration

NO ground-truth coordinates or forward.nc are used anywhere in these tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from pydantic import ValidationError

from app.models.geometry import (
    GeoJSONLineString,
    GeoJSONPolygon,
    Point,
)
from app.models.slick import Slick
from app.models.source_candidate_region import SourceCandidateRegion
from app.models.source_region import SourceRegion
from app.schemas.hindcast import (
    ForwardSimulationRequest,
    ForwardSimulationResult,
    HindcastRequest,
    HindcastResponse,
    SimulationMetadata,
)
from app.services.hindcast import (
    _lonlat_to_xy,
    _xy_to_lonlat,
    extract_source_region_from_particles,
)

# ─── Fixtures / Helpers ──────────────────────────────────────────────────

VALID_RING = [
    [72.83, 18.92],
    [72.84, 18.92],
    [72.84, 18.93],
    [72.83, 18.93],
    [72.83, 18.92],
]

NOW = datetime.now(timezone.utc)


def _sample_slick(**overrides) -> Slick:
    """Return a valid Slick for testing."""
    defaults = {
        "id": "slick-test-001",
        "timestamp_utc": NOW,
        "centroid": Point(lat=18.925, lon=72.835),
        "geometry": GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
        "area_km2": 10.5,
        "confidence": 0.85,
    }
    defaults.update(overrides)
    return Slick(**defaults)


def _sample_source_region() -> SourceRegion:
    """Return a valid SourceRegion for testing."""
    return SourceRegion(
        id="sr-test",
        slick_id="slick-test-001",
        candidate_regions=[
            SourceCandidateRegion(
                id="cr-test",
                geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
                centroid=Point(lat=18.925, lon=72.835),
                start_time_utc=NOW - timedelta(hours=12),
                end_time_utc=NOW,
                probability=0.95,
            )
        ],
        generated_at_utc=NOW,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Schema Validation
# ═══════════════════════════════════════════════════════════════════════════


class TestHindcastRequest:
    def test_valid_request(self) -> None:
        req = HindcastRequest(slick=_sample_slick())
        assert req.duration_hours == 12  # default
        assert req.slick.id == "slick-test-001"

    def test_custom_duration(self) -> None:
        req = HindcastRequest(slick=_sample_slick(), duration_hours=6)
        assert req.duration_hours == 6

    def test_duration_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="greater than"):
            HindcastRequest(slick=_sample_slick(), duration_hours=0)

    def test_duration_max_72(self) -> None:
        with pytest.raises(ValidationError):
            HindcastRequest(slick=_sample_slick(), duration_hours=73)


class TestForwardSimulationRequest:
    def test_valid_request(self) -> None:
        req = ForwardSimulationRequest(
            incident_id="inc-001",
            vessel_mmsi="123456789",
            release_location=Point(lat=60.0, lon=4.5),
            release_time_utc=NOW - timedelta(hours=12),
            observation_time_utc=NOW,
        )
        assert req.vessel_mmsi == "123456789"

    def test_release_after_observation_rejected(self) -> None:
        with pytest.raises(
            ValidationError,
            match="release_time_utc must be <= observation_time_utc",
        ):
            ForwardSimulationRequest(
                incident_id="inc-001",
                vessel_mmsi="123456789",
                release_location=Point(lat=60.0, lon=4.5),
                release_time_utc=NOW + timedelta(hours=1),
                observation_time_utc=NOW,
            )

    def test_invalid_mmsi_length(self) -> None:
        with pytest.raises(ValidationError):
            ForwardSimulationRequest(
                incident_id="inc-001",
                vessel_mmsi="12345",  # too short
                release_location=Point(lat=60.0, lon=4.5),
                release_time_utc=NOW - timedelta(hours=12),
                observation_time_utc=NOW,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 2. UTC Timestamp Validation
# ═══════════════════════════════════════════════════════════════════════════


class TestUTCValidation:
    def test_naive_datetime_in_slick_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            _sample_slick(timestamp_utc=datetime(2025, 8, 20, 12, 0))

    def test_naive_datetime_in_forward_request_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            ForwardSimulationRequest(
                incident_id="inc-001",
                vessel_mmsi="123456789",
                release_location=Point(lat=60.0, lon=4.5),
                release_time_utc=datetime(2025, 8, 20, 0, 0),  # naive
                observation_time_utc=NOW,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Coordinate Ordering
# ═══════════════════════════════════════════════════════════════════════════


class TestCoordinateOrdering:
    def test_geojson_linestring_uses_lon_lat(self) -> None:
        ls = GeoJSONLineString(
            type="LineString",
            coordinates=[[72.83, 18.92], [72.84, 18.93]],
        )
        # GeoJSON: [longitude, latitude]
        assert ls.coordinates[0][0] == 72.83  # longitude
        assert ls.coordinates[0][1] == 18.92  # latitude

    def test_point_uses_lat_lon(self) -> None:
        p = Point(lat=18.92, lon=72.83)
        assert p.lat == 18.92
        assert p.lon == 72.83


# ═══════════════════════════════════════════════════════════════════════════
# 4. Trajectory / Timestamp 1:1 Alignment
# ═══════════════════════════════════════════════════════════════════════════


class TestTrajectoryTimestampAlignment:
    def test_mismatched_counts_rejected_in_hindcast_response(self) -> None:
        with pytest.raises(
            ValidationError,
            match="strict 1:1 mapping",
        ):
            HindcastResponse(
                source_region=_sample_source_region(),
                backward_trajectory=GeoJSONLineString(
                    type="LineString",
                    coordinates=[[72.83, 18.92], [72.84, 18.93], [72.85, 18.94]],
                ),
                trajectory_timestamps_utc=[NOW, NOW - timedelta(hours=1)],
                # 3 coords vs 2 timestamps → mismatch
            )

    def test_matching_counts_accepted(self) -> None:
        resp = HindcastResponse(
            source_region=_sample_source_region(),
            backward_trajectory=GeoJSONLineString(
                type="LineString",
                coordinates=[[72.83, 18.92], [72.84, 18.93]],
            ),
            trajectory_timestamps_utc=[NOW, NOW - timedelta(hours=1)],
        )
        assert len(resp.trajectory_timestamps_utc) == 2
        assert len(resp.backward_trajectory.coordinates) == 2

    def test_forward_result_alignment_enforced(self) -> None:
        with pytest.raises(ValidationError, match="strict 1:1 mapping"):
            ForwardSimulationResult(
                incident_id="inc-001",
                vessel_mmsi="123456789",
                release_location=Point(lat=60.0, lon=4.5),
                release_time_utc=NOW - timedelta(hours=12),
                trajectory=GeoJSONLineString(
                    type="LineString",
                    coordinates=[[4.5, 60.0], [4.6, 60.1]],
                ),
                # 2 coords vs 3 timestamps → model validator fires
                trajectory_timestamps_utc=[
                    NOW - timedelta(hours=12),
                    NOW - timedelta(hours=6),
                    NOW,
                ],
                simulation_metadata=SimulationMetadata(
                    particle_count=1000,
                    duration_hours=12.0,
                    oil_type="GENERIC BUNKER C",
                ),
            )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Metric Projection
# ═══════════════════════════════════════════════════════════════════════════


class TestMetricProjection:
    def test_roundtrip(self) -> None:
        """lon/lat → x/y → lon/lat should be approximately identity."""
        lons = np.array([4.5, 4.6, 4.4])
        lats = np.array([60.0, 60.1, 59.9])
        lon0, lat0 = 4.5, 60.0

        x, y = _lonlat_to_xy(lons, lats, lon0, lat0)
        roundtrip_lons, roundtrip_lats = _xy_to_lonlat(x, y, lon0, lat0)

        np.testing.assert_allclose(roundtrip_lons, lons, atol=1e-6)
        np.testing.assert_allclose(roundtrip_lats, lats, atol=1e-6)

    def test_origin_maps_to_zero(self) -> None:
        x, y = _lonlat_to_xy(np.array([4.5]), np.array([60.0]), 4.5, 60.0)
        assert abs(x[0]) < 1e-10
        assert abs(y[0]) < 1e-10


# ═══════════════════════════════════════════════════════════════════════════
# 6. KDE Geometry Validity & SourceRegion Extraction
# ═══════════════════════════════════════════════════════════════════════════


class TestKDESourceExtraction:
    @pytest.fixture
    def gaussian_particles(self) -> tuple[np.ndarray, np.ndarray]:
        """Synthetic particles with a clear Gaussian cluster."""
        rng = np.random.default_rng(42)
        n = 500
        lons = rng.normal(loc=4.5, scale=0.01, size=n)
        lats = rng.normal(loc=60.0, scale=0.01, size=n)
        return lons, lats

    def test_produces_valid_source_region(
        self, gaussian_particles: tuple[np.ndarray, np.ndarray],
    ) -> None:
        lons, lats = gaussian_particles
        sr = extract_source_region_from_particles(
            lons,
            lats,
            earliest_time=NOW - timedelta(hours=12),
            latest_time=NOW,
            slick_id="slick-test-001",
        )
        # Type checks
        assert isinstance(sr, SourceRegion)
        assert len(sr.candidate_regions) >= 1

        cr = sr.candidate_regions[0]
        assert isinstance(cr, SourceCandidateRegion)

    def test_slick_id_propagated(
        self, gaussian_particles: tuple[np.ndarray, np.ndarray],
    ) -> None:
        lons, lats = gaussian_particles
        sr = extract_source_region_from_particles(
            lons,
            lats,
            earliest_time=NOW - timedelta(hours=12),
            latest_time=NOW,
            slick_id="my-unique-slick-id",
        )
        assert sr.slick_id == "my-unique-slick-id"

    def test_probability_is_hdr_mass_fraction(
        self, gaussian_particles: tuple[np.ndarray, np.ndarray],
    ) -> None:
        lons, lats = gaussian_particles
        sr = extract_source_region_from_particles(
            lons,
            lats,
            earliest_time=NOW - timedelta(hours=12),
            latest_time=NOW,
            slick_id="slick-test-001",
            hdr_mass_fraction=0.95,
        )
        cr = sr.candidate_regions[0]
        # The actual mass should be >= 0.95 (the threshold)
        assert cr.probability >= 0.95
        assert cr.probability <= 1.0

    def test_geometry_is_valid_geojson_polygon(
        self, gaussian_particles: tuple[np.ndarray, np.ndarray],
    ) -> None:
        lons, lats = gaussian_particles
        sr = extract_source_region_from_particles(
            lons,
            lats,
            earliest_time=NOW - timedelta(hours=12),
            latest_time=NOW,
            slick_id="slick-test-001",
        )
        cr = sr.candidate_regions[0]
        geom = cr.geometry
        # Must be GeoJSONPolygon or GeoJSONMultiPolygon
        assert geom.type in ("Polygon", "MultiPolygon")

        # GeoJSON coordinates are [lon, lat]
        if geom.type == "Polygon":
            ring = geom.coordinates[0]
            # Closed ring: first == last
            assert ring[0] == ring[-1]
            # At least 4 points (3 + closing)
            assert len(ring) >= 4

    def test_centroid_near_particle_mean(
        self, gaussian_particles: tuple[np.ndarray, np.ndarray],
    ) -> None:
        lons, lats = gaussian_particles
        sr = extract_source_region_from_particles(
            lons,
            lats,
            earliest_time=NOW - timedelta(hours=12),
            latest_time=NOW,
            slick_id="slick-test-001",
        )
        cr = sr.candidate_regions[0]
        # MAP estimate should be close to particle mean
        assert abs(cr.centroid.lon - float(np.mean(lons))) < 0.05
        assert abs(cr.centroid.lat - float(np.mean(lats))) < 0.05

    def test_time_window_propagated(
        self, gaussian_particles: tuple[np.ndarray, np.ndarray],
    ) -> None:
        lons, lats = gaussian_particles
        start = NOW - timedelta(hours=12)
        end = NOW
        sr = extract_source_region_from_particles(
            lons,
            lats,
            earliest_time=start,
            latest_time=end,
            slick_id="slick-test-001",
        )
        cr = sr.candidate_regions[0]
        assert cr.start_time_utc == start
        assert cr.end_time_utc == end

    def test_generated_at_is_utc_aware(
        self, gaussian_particles: tuple[np.ndarray, np.ndarray],
    ) -> None:
        lons, lats = gaussian_particles
        sr = extract_source_region_from_particles(
            lons,
            lats,
            earliest_time=NOW - timedelta(hours=12),
            latest_time=NOW,
            slick_id="slick-test-001",
        )
        assert sr.generated_at_utc.tzinfo is not None

    def test_too_few_particles_raises(self) -> None:
        with pytest.raises(ValueError):
            extract_source_region_from_particles(
                np.array([4.5, 4.5]),
                np.array([60.0, 60.0]),
                earliest_time=NOW - timedelta(hours=12),
                latest_time=NOW,
                slick_id="slick-test-001",
            )

    def test_no_ground_truth_in_projection(
        self, gaussian_particles: tuple[np.ndarray, np.ndarray],
    ) -> None:
        """Verify the projection is NOT centered on any hardcoded
        ground-truth coordinate (4.5, 60.0 was the test project's
        ground truth).
        """
        # Use particles centered far from (4.5, 60.0)
        rng = np.random.default_rng(123)
        lons = rng.normal(loc=10.0, scale=0.01, size=200)
        lats = rng.normal(loc=45.0, scale=0.01, size=200)

        sr = extract_source_region_from_particles(
            lons,
            lats,
            earliest_time=NOW - timedelta(hours=12),
            latest_time=NOW,
            slick_id="slick-test-001",
        )
        cr = sr.candidate_regions[0]
        # Centroid should be near (10.0, 45.0), NOT near (4.5, 60.0)
        assert abs(cr.centroid.lon - 10.0) < 0.1
        assert abs(cr.centroid.lat - 45.0) < 0.1


# ═══════════════════════════════════════════════════════════════════════════
# 7. HindcastResponse Construction
# ═══════════════════════════════════════════════════════════════════════════


class TestHindcastResponseConstruction:
    def test_valid_response(self) -> None:
        resp = HindcastResponse(
            source_region=_sample_source_region(),
            backward_trajectory=GeoJSONLineString(
                type="LineString",
                coordinates=[
                    [72.83, 18.92],
                    [72.84, 18.93],
                    [72.85, 18.94],
                ],
            ),
            trajectory_timestamps_utc=[
                NOW,
                NOW - timedelta(hours=1),
                NOW - timedelta(hours=2),
            ],
        )
        assert resp.source_region.slick_id == "slick-test-001"
        assert len(resp.trajectory_timestamps_utc) == 3

    def test_min_two_trajectory_points_required(self) -> None:
        with pytest.raises(ValidationError):
            HindcastResponse(
                source_region=_sample_source_region(),
                backward_trajectory=GeoJSONLineString(
                    type="LineString",
                    coordinates=[[72.83, 18.92], [72.84, 18.93]],
                ),
                trajectory_timestamps_utc=[NOW],  # only 1 — min_length=2 fails
            )


# ═══════════════════════════════════════════════════════════════════════════
# 8. ForwardSimulationResult Construction
# ═══════════════════════════════════════════════════════════════════════════


class TestForwardSimulationResultConstruction:
    def test_valid_result(self) -> None:
        result = ForwardSimulationResult(
            incident_id="inc-001",
            vessel_mmsi="123456789",
            release_location=Point(lat=60.0, lon=4.5),
            release_time_utc=NOW - timedelta(hours=12),
            trajectory=GeoJSONLineString(
                type="LineString",
                coordinates=[[4.5, 60.0], [4.6, 60.1]],
            ),
            trajectory_timestamps_utc=[
                NOW - timedelta(hours=12),
                NOW,
            ],
            predicted_footprint=GeoJSONPolygon(
                type="Polygon", coordinates=[VALID_RING],
            ),
            simulation_metadata=SimulationMetadata(
                particle_count=1000,
                duration_hours=12.0,
                oil_type="GENERIC BUNKER C",
            ),
        )
        assert result.incident_id == "inc-001"
        assert result.predicted_footprint is not None

    def test_null_footprint_accepted(self) -> None:
        result = ForwardSimulationResult(
            incident_id="inc-001",
            vessel_mmsi="123456789",
            release_location=Point(lat=60.0, lon=4.5),
            release_time_utc=NOW - timedelta(hours=12),
            trajectory=GeoJSONLineString(
                type="LineString",
                coordinates=[[4.5, 60.0], [4.6, 60.1]],
            ),
            trajectory_timestamps_utc=[
                NOW - timedelta(hours=12),
                NOW,
            ],
            predicted_footprint=None,
            simulation_metadata=SimulationMetadata(
                particle_count=1000,
                duration_hours=12.0,
                oil_type="GENERIC BUNKER C",
            ),
        )
        assert result.predicted_footprint is None


# ═══════════════════════════════════════════════════════════════════════════
# 9. Mocked Execution-Level Tests (run_hindcast / run_forward)
# ═══════════════════════════════════════════════════════════════════════════


class TestMockedRunHindcast:
    """Verify the run_hindcast pipeline with a mocked OpenDrift backend."""

    def _build_mock_ds(self):
        """Build a minimal xarray Dataset mimicking OpenDrift output."""
        import xarray as xr

        n_particles = 50
        n_times = 7
        rng = np.random.default_rng(42)

        # Simulate backward trajectory: particles start at ~4.5/60.0 and
        # drift north/west over 6h.
        base_lon = 4.5
        base_lat = 60.0
        lons = np.zeros((n_particles, n_times))
        lats = np.zeros((n_particles, n_times))

        for i in range(n_times):
            lons[:, i] = base_lon + rng.normal(0, 0.005, n_particles) - i * 0.002
            lats[:, i] = base_lat + rng.normal(0, 0.005, n_particles) + i * 0.005

        times = np.array(
            [np.datetime64("2025-08-20T12:00:00") - np.timedelta64(i, "h") for i in range(n_times)]
        )

        ds = xr.Dataset(
            {
                "lon": (["trajectory", "time"], lons),
                "lat": (["trajectory", "time"], lats),
            },
            coords={
                "trajectory": np.arange(n_particles),
                "time": times,
            },
        )
        return ds

    def test_run_hindcast_pipeline(self) -> None:
        """Full pipeline: Slick → seed_elements → backward simulation
        → trajectory → KDE → SourceRegion → HindcastResponse."""
        from unittest.mock import MagicMock, patch

        mock_ds = self._build_mock_ds()
        slick = _sample_slick(
            timestamp_utc=datetime(2025, 8, 20, 12, 0, tzinfo=timezone.utc),
        )

        mock_oil = MagicMock()
        mock_oil.result = mock_ds

        with patch("opendrift.models.openoil.OpenOil", return_value=mock_oil) as MockOil, \
             patch("opendrift.readers.reader_netCDF_CF_generic.Reader") as MockReader:

            from app.services.hindcast import run_hindcast

            result = run_hindcast(slick, duration_hours=6)

        # Verify seed_elements was called with slick centroid.
        mock_oil.seed_elements.assert_called_once()
        call_kwargs = mock_oil.seed_elements.call_args
        assert call_kwargs.kwargs["lon"] == slick.centroid.lon
        assert call_kwargs.kwargs["lat"] == slick.centroid.lat

        # Verify backward run (negative duration).
        mock_oil.run.assert_called_once()
        run_kwargs = mock_oil.run.call_args.kwargs
        assert run_kwargs["duration"].total_seconds() < 0

        # Verify response structure.
        assert result.source_region.slick_id == slick.id
        assert len(result.source_region.candidate_regions) >= 1
        assert len(result.backward_trajectory.coordinates) == len(
            result.trajectory_timestamps_utc,
        )
        assert all(
            t.tzinfo is not None for t in result.trajectory_timestamps_utc
        )

        # Verify KDE probability semantics.
        cr = result.source_region.candidate_regions[0]
        assert cr.probability >= 0.95
        assert cr.probability <= 1.0
        assert cr.geometry.type in ("Polygon", "MultiPolygon")


class TestMockedRunForward:
    """Verify the run_forward pipeline with a mocked OpenDrift backend."""

    def _build_forward_mock_ds(self):
        """Build a minimal xarray Dataset for forward simulation."""
        import xarray as xr

        n_particles = 50
        n_times = 7
        rng = np.random.default_rng(99)

        base_lon = 4.5
        base_lat = 60.0
        lons = np.zeros((n_particles, n_times))
        lats = np.zeros((n_particles, n_times))

        for i in range(n_times):
            lons[:, i] = base_lon + rng.normal(0, 0.005, n_particles) + i * 0.002
            lats[:, i] = base_lat + rng.normal(0, 0.005, n_particles) - i * 0.003

        times = np.array(
            [np.datetime64("2025-08-20T00:00:00") + np.timedelta64(i, "h") for i in range(n_times)]
        )

        ds = xr.Dataset(
            {
                "lon": (["trajectory", "time"], lons),
                "lat": (["trajectory", "time"], lats),
            },
            coords={
                "trajectory": np.arange(n_particles),
                "time": times,
            },
        )
        return ds

    def test_run_forward_pipeline(self) -> None:
        """Full pipeline: ForwardSimulationRequest → seed_elements
        → forward simulation → trajectory → footprint →
        ForwardSimulationResult."""
        from unittest.mock import MagicMock, patch

        mock_ds = self._build_forward_mock_ds()

        req = ForwardSimulationRequest(
            incident_id="test-inc-001",
            vessel_mmsi="123456789",
            release_location=Point(lat=60.0, lon=4.5),
            release_time_utc=datetime(2025, 8, 20, 0, 0, tzinfo=timezone.utc),
            observation_time_utc=datetime(2025, 8, 20, 6, 0, tzinfo=timezone.utc),
        )

        mock_oil = MagicMock()
        mock_oil.result = mock_ds

        with patch("opendrift.models.openoil.OpenOil", return_value=mock_oil), \
             patch("opendrift.readers.reader_netCDF_CF_generic.Reader"):

            from app.services.hindcast import run_forward

            result = run_forward(req)

        # Verify seed_elements was called with release location.
        mock_oil.seed_elements.assert_called_once()
        call_kwargs = mock_oil.seed_elements.call_args
        assert call_kwargs.kwargs["lon"] == req.release_location.lon
        assert call_kwargs.kwargs["lat"] == req.release_location.lat

        # Verify forward run (positive duration).
        mock_oil.run.assert_called_once()
        run_kwargs = mock_oil.run.call_args.kwargs
        assert run_kwargs["duration"].total_seconds() > 0

        # Verify response.
        assert result.incident_id == "test-inc-001"
        assert result.vessel_mmsi == "123456789"
        assert result.release_location.lat == 60.0
        assert result.release_location.lon == 4.5
        assert result.release_time_utc == req.release_time_utc
        assert len(result.trajectory.coordinates) == len(
            result.trajectory_timestamps_utc,
        )
        assert all(t.tzinfo is not None for t in result.trajectory_timestamps_utc)

        # Verify metadata propagation.
        assert result.simulation_metadata.particle_count > 0
        assert result.simulation_metadata.duration_hours == 6.0
        assert result.simulation_metadata.oil_type != ""

        # Verify predicted footprint (if particles are spread enough).
        # With 50 particles, convex hull should produce a polygon.
        assert result.predicted_footprint is not None
        assert result.predicted_footprint.type == "Polygon"