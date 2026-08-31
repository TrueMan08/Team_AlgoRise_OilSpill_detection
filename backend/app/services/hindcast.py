"""Drift simulation service — backward hindcast and forward counterfactual.

Production-relevant logic extracted from the tested ``oil_drift_test``
methodology.  Ground-truth coordinates, plotting, and forward.nc
dependencies have been deliberately removed.

Scientific notes
~~~~~~~~~~~~~~~~
*  ``SourceCandidateRegion.probability`` carries a **KDE density mass
   fraction** (e.g. 0.95 for the 95% HDR).  It is NOT a calibrated
   probability that the true source lies within the region.
*  The metric projection is centered on the **particle mean** — not on
   any external ground-truth coordinate.
*  Contour geometries are healed with ``.buffer(0)`` to fix any
   self-intersections produced by matplotlib's contouring algorithm.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")  # headless — no GUI required

import matplotlib.pyplot as plt  # noqa: E402
from scipy.stats import gaussian_kde  # noqa: E402
from shapely.geometry import (  # noqa: E402
    MultiPolygon,
    Polygon,
    mapping,
)

from app.core.config import settings  # noqa: E402
from app.models.geometry import (  # noqa: E402
    GeoJSONLineString,
    GeoJSONPolygon,
    GeoJSONMultiPolygon,
    Point,
)
from app.models.slick import Slick  # noqa: E402
from app.models.source_candidate_region import SourceCandidateRegion  # noqa: E402
from app.models.source_region import SourceRegion  # noqa: E402
from app.schemas.hindcast import (  # noqa: E402
    ForwardSimulationRequest,
    ForwardSimulationResult,
    HindcastResponse,
    SimulationMetadata,
)

logger = logging.getLogger("oilspill_backend.hindcast")

# Mean Earth radius (km) — used for metric projection.
_EARTH_RADIUS_KM = 6371.0


# ---------------------------------------------------------------------------
# Metric projection helpers  (centered on *runtime-derived* reference point)
# ---------------------------------------------------------------------------


def _lonlat_to_xy(
    lons: np.ndarray,
    lats: np.ndarray,
    lon0: float,
    lat0: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert WGS-84 lon/lat to local tangent-plane km coordinates."""
    lat0_rad = np.radians(lat0)
    x = _EARTH_RADIUS_KM * np.cos(lat0_rad) * np.radians(lons - lon0)
    y = _EARTH_RADIUS_KM * np.radians(lats - lat0)
    return x, y


def _xy_to_lonlat(
    x: np.ndarray,
    y: np.ndarray,
    lon0: float,
    lat0: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert local tangent-plane km coordinates back to WGS-84."""
    lat0_rad = np.radians(lat0)
    lons = lon0 + np.degrees(x / (_EARTH_RADIUS_KM * np.cos(lat0_rad)))
    lats = lat0 + np.degrees(y / _EARTH_RADIUS_KM)
    return lons, lats


# ---------------------------------------------------------------------------
# KDE / source-region extraction (reusable, no OpenDrift dependency)
# ---------------------------------------------------------------------------


def extract_source_region_from_particles(
    lons: np.ndarray,
    lats: np.ndarray,
    *,
    earliest_time: datetime,
    latest_time: datetime,
    slick_id: str,
    grid_resolution: int | None = None,
    margin_km: float | None = None,
    hdr_mass_fraction: float | None = None,
) -> SourceRegion:
    """Run 2-D KDE on backward-reconstructed particle positions and
    extract the highest-density region as ``SourceCandidateRegion``
    objects wrapped in a ``SourceRegion``.

    Parameters
    ----------
    lons, lats
        1-D arrays of valid (non-NaN) particle positions at the
        earliest reconstruction timestep.
    earliest_time
        Chronologically earliest time in the backward simulation
        (the reconstruction time — release-window start).
    latest_time
        The observation / slick detection time
        (release-window end).
    slick_id
        Propagated as ``SourceRegion.slick_id``.
    grid_resolution
        Number of grid cells per axis.  Defaults to config.
    margin_km
        Margin beyond particle extent (km).  Defaults to config.
    hdr_mass_fraction
        Target density mass fraction (0–1).  Defaults to config.

    Returns
    -------
    SourceRegion
        With at least one ``SourceCandidateRegion`` whose
        ``probability`` field carries the HDR mass fraction — a
        **density mass fraction**, NOT a calibrated probability.
    """
    grid_resolution = grid_resolution or settings.DRIFT_KDE_GRID_RESOLUTION
    margin_km = margin_km if margin_km is not None else settings.DRIFT_KDE_MARGIN_KM
    hdr_mass_fraction = (
        hdr_mass_fraction
        if hdr_mass_fraction is not None
        else settings.DRIFT_KDE_HDR_MASS_FRACTION
    )

    # ── Metric projection centered on particle mean ──────────────────
    lon0 = float(np.mean(lons))
    lat0 = float(np.mean(lats))
    valid_x, valid_y = _lonlat_to_xy(lons, lats, lon0, lat0)

    # ── Gaussian KDE ─────────────────────────────────────────────────
    positions_xy = np.vstack([valid_x, valid_y])
    kde = gaussian_kde(positions_xy)

    x_min = valid_x.min() - margin_km
    x_max = valid_x.max() + margin_km
    y_min = valid_y.min() - margin_km
    y_max = valid_y.max() + margin_km

    x_grid, y_grid = np.mgrid[
        x_min : x_max : complex(grid_resolution),
        y_min : y_max : complex(grid_resolution),
    ]
    grid_coords = np.vstack([x_grid.ravel(), y_grid.ravel()])

    kde_values = kde(grid_coords)
    kde_surface = np.reshape(kde_values, x_grid.shape)

    # ── MAP (maximum a-posteriori density) estimate ──────────────────
    max_idx = np.argmax(kde_surface)
    max_idx_2d = np.unravel_index(max_idx, kde_surface.shape)
    map_x = float(x_grid[max_idx_2d])
    map_y = float(y_grid[max_idx_2d])
    map_lon, map_lat = _xy_to_lonlat(
        np.array([map_x]), np.array([map_y]), lon0, lat0,
    )
    map_lon = float(map_lon[0])
    map_lat = float(map_lat[0])

    # ── 95% HDR threshold ────────────────────────────────────────────
    kde_normalized = kde_surface / np.sum(kde_surface)
    sorted_probs = np.sort(kde_normalized.flatten())[::-1]
    sorted_densities = np.sort(kde_surface.flatten())[::-1]
    cumulative_probs = np.cumsum(sorted_probs)

    idx_threshold = int(np.argmax(cumulative_probs >= hdr_mass_fraction))
    hdr_density_threshold = float(sorted_densities[idx_threshold])
    actual_mass = float(cumulative_probs[idx_threshold])

    logger.info(
        "KDE HDR: threshold=%.4e, actual_mass=%.4f, "
        "MAP=(%.4f, %.4f)",
        hdr_density_threshold,
        actual_mass,
        map_lon,
        map_lat,
    )

    # ── Contour extraction (matplotlib, headless) ────────────────────
    fig, ax = plt.subplots()
    cs = ax.contour(x_grid, y_grid, kde_surface, levels=[hdr_density_threshold])
    plt.close(fig)

    paths = cs.get_paths()
    polygons: list[Polygon] = []

    for path in paths:
        for poly_pts in path.to_polygons():
            poly_lons, poly_lats = _xy_to_lonlat(
                poly_pts[:, 0], poly_pts[:, 1], lon0, lat0,
            )
            # Ensure closed ring.
            if poly_lons[0] != poly_lons[-1] or poly_lats[0] != poly_lats[-1]:
                poly_lons = np.append(poly_lons, poly_lons[0])
                poly_lats = np.append(poly_lats, poly_lats[0])

            coords = [
                (float(lon), float(lat))
                for lon, lat in zip(poly_lons, poly_lats)
            ]
            if len(coords) >= 4:  # 3 unique + 1 closing
                polygons.append(Polygon(coords))

    if not polygons:
        raise ValueError(
            "KDE contour extraction produced no valid polygons — "
            "check particle positions and KDE parameters."
        )

    # Assemble geometry, heal self-intersections.
    if len(polygons) == 1:
        final_geom = polygons[0].buffer(0)
    else:
        final_geom = MultiPolygon(polygons).buffer(0)

    if not final_geom.is_valid:
        raise ValueError(
            f"Source-region geometry failed Shapely validation: "
            f"{final_geom.geom_type}"
        )

    geom_dict = mapping(final_geom)
    if geom_dict["type"] == "Polygon":
        geometry_model = GeoJSONPolygon(**geom_dict)
    elif geom_dict["type"] == "MultiPolygon":
        geometry_model = GeoJSONMultiPolygon(**geom_dict)
    else:
        raise ValueError(f"Unexpected geometry type: {geom_dict['type']}")

    # ── Build domain objects ─────────────────────────────────────────
    candidate = SourceCandidateRegion(
        id=f"cr-{uuid.uuid4().hex[:12]}",
        geometry=geometry_model,
        centroid=Point(lat=map_lat, lon=map_lon),
        start_time_utc=earliest_time,
        end_time_utc=latest_time,
        # IMPORTANT: This is a KDE density mass fraction, NOT a
        # calibrated probability that the true source is inside.
        probability=round(actual_mass, 4),
    )

    source_region = SourceRegion(
        id=f"sr-{uuid.uuid4().hex[:12]}",
        slick_id=slick_id,
        candidate_regions=[candidate],
        generated_at_utc=datetime.now(timezone.utc),
    )

    return source_region


# ---------------------------------------------------------------------------
# Trajectory extraction helpers
# ---------------------------------------------------------------------------


def _extract_trajectory_summary(
    ds: Any,
) -> tuple[list[list[float]], list[datetime]]:
    """Extract a per-timestep centroid path from an OpenDrift xarray
    Dataset.

    Returns
    -------
    coordinates
        List of ``[longitude, latitude]`` pairs (GeoJSON order).
    timestamps
        List of timezone-aware UTC datetimes, 1:1 with coordinates.
    """
    times = ds.time.values
    coordinates: list[list[float]] = []
    timestamps: list[datetime] = []

    for t in times:
        ds_t = ds.sel(time=t)
        t_lons = ds_t.lon.values
        t_lats = ds_t.lat.values

        valid = ~np.isnan(t_lons) & ~np.isnan(t_lats)
        if not np.any(valid):
            continue

        mean_lon = float(np.mean(t_lons[valid]))
        mean_lat = float(np.mean(t_lats[valid]))
        coordinates.append([mean_lon, mean_lat])

        # numpy datetime64 → Python datetime (UTC-aware)
        ts = np.datetime64(t, "ns")
        dt = ts.astype("datetime64[ms]").astype(datetime)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        timestamps.append(dt)

    return coordinates, timestamps


# ---------------------------------------------------------------------------
# run_hindcast  —  PRODUCTION BACKWARD SIMULATION
# ---------------------------------------------------------------------------


def run_hindcast(slick: Slick, duration_hours: int | None = None) -> HindcastResponse:
    """Run a backward OpenOil simulation seeded from the detected slick
    and return the reconstructed source region plus a lightweight
    trajectory summary.

    The simulation seeds from ``slick.centroid`` using
    ``seed_elements()`` — it does NOT depend on any previous forward.nc.

    Parameters
    ----------
    slick
        The detected oil slick (from ``POST /detect``).
    duration_hours
        How many hours to trace backward.  Defaults to the configured
        ``DRIFT_DEFAULT_DURATION_HOURS``.
    """
    from opendrift.models.openoil import OpenOil
    from opendrift.readers import reader_netCDF_CF_generic

    duration_hours = duration_hours or settings.DRIFT_DEFAULT_DURATION_HOURS

    logger.info(
        "Starting backward hindcast: slick=%s, duration=%dh, "
        "particles=%d",
        slick.id,
        duration_hours,
        settings.DRIFT_PARTICLE_COUNT,
    )

    # ── 1. Create model ──────────────────────────────────────────────
    o = OpenOil(loglevel=20, seed=42)
    o.set_oiltype(settings.DRIFT_OIL_TYPE)
    o.keep_droplet_diameter = False
    o.set_config("drift:vertical_mixing", False)

    # ── 2. Add forcing readers ───────────────────────────────────────
    current_reader = reader_netCDF_CF_generic.Reader(
        settings.DRIFT_FORCING_CURRENTS_PATH,
    )
    wind_reader = reader_netCDF_CF_generic.Reader(
        settings.DRIFT_FORCING_WIND_PATH,
    )
    readers = [current_reader, wind_reader]
    if settings.DRIFT_LANDMASK_PATH:  # optional override; default auto-landmask
        readers.append(
            reader_netCDF_CF_generic.Reader(settings.DRIFT_LANDMASK_PATH))
    o.add_reader(readers)

    # ── 3. Seed from Slick (NOT from forward.nc) ─────────────────────
    observation_time = slick.timestamp_utc.replace(tzinfo=None)

    o.seed_elements(
        lon=slick.centroid.lon,
        lat=slick.centroid.lat,
        number=settings.DRIFT_PARTICLE_COUNT,
        radius=1000,  # 1 km spread around centroid
        time=observation_time,
    )

    # ── 4. Run backward ──────────────────────────────────────────────
    o.run(
        duration=timedelta(hours=-duration_hours),
        time_step=timedelta(minutes=-settings.DRIFT_TIMESTEP_MINUTES),
        time_step_output=timedelta(minutes=-settings.DRIFT_OUTPUT_INTERVAL_MINUTES),
    )

    # ── 5. Read results from in-memory dataset ───────────────────────
    ds = o.result

    # Extract trajectory summary (centroid at each saved timestep).
    traj_coords, traj_timestamps = _extract_trajectory_summary(ds)

    if len(traj_coords) < 2:
        raise ValueError(
            "Backward simulation produced fewer than 2 trajectory "
            "points — check forcing data coverage."
        )

    # ── 6. Extract particle positions at earliest time ───────────────
    times = ds.time.values
    earliest_time_np = np.min(times)
    ds_earliest = ds.sel(time=earliest_time_np)

    earliest_lons = ds_earliest.lon.values
    earliest_lats = ds_earliest.lat.values

    valid_mask = ~np.isnan(earliest_lons) & ~np.isnan(earliest_lats)
    valid_lons = earliest_lons[valid_mask]
    valid_lats = earliest_lats[valid_mask]

    if len(valid_lons) < 3:
        raise ValueError(
            f"Only {len(valid_lons)} valid particles at earliest "
            f"timestep — insufficient for KDE."
        )

    logger.info(
        "Backward simulation complete: %d valid particles at "
        "earliest time",
        len(valid_lons),
    )

    # Convert earliest time to Python datetime (UTC-aware).
    earliest_dt = (
        np.datetime64(earliest_time_np, "ns")
        .astype("datetime64[ms]")
        .astype(datetime)
    )
    if earliest_dt.tzinfo is None:
        earliest_dt = earliest_dt.replace(tzinfo=timezone.utc)

    observation_time_utc = slick.timestamp_utc
    if observation_time_utc.tzinfo is None:
        observation_time_utc = observation_time_utc.replace(
            tzinfo=timezone.utc,
        )

    # ── 7. KDE → SourceRegion ────────────────────────────────────────
    source_region = extract_source_region_from_particles(
        valid_lons,
        valid_lats,
        earliest_time=earliest_dt,
        latest_time=observation_time_utc,
        slick_id=slick.id,
    )

    # ── 8. Build response ────────────────────────────────────────────
    backward_trajectory = GeoJSONLineString(
        type="LineString",
        coordinates=traj_coords,
    )

    return HindcastResponse(
        source_region=source_region,
        backward_trajectory=backward_trajectory,
        trajectory_timestamps_utc=traj_timestamps,
    )


# ---------------------------------------------------------------------------
# run_forward  —  FORWARD COUNTERFACTUAL SIMULATION
# ---------------------------------------------------------------------------


def run_forward(request: ForwardSimulationRequest) -> ForwardSimulationResult:
    """Run a forward OpenOil simulation from a candidate release state
    to check physical plausibility against the observed slick.

    The release location and time come from Nimit's attribution output.
    """
    from opendrift.models.openoil import OpenOil
    from opendrift.readers import reader_netCDF_CF_generic

    duration = request.observation_time_utc - request.release_time_utc
    duration_hours = duration.total_seconds() / 3600.0

    if duration_hours <= 0:
        raise ValueError(
            "observation_time_utc must be after release_time_utc."
        )

    logger.info(
        "Starting forward simulation: vessel=%s, duration=%.1fh",
        request.vessel_mmsi,
        duration_hours,
    )

    # ── 1. Create model ──────────────────────────────────────────────
    o = OpenOil(loglevel=20, seed=42)
    o.set_oiltype(settings.DRIFT_OIL_TYPE)
    o.keep_droplet_diameter = False
    o.set_config("drift:vertical_mixing", False)

    # ── 2. Add forcing readers ───────────────────────────────────────
    current_reader = reader_netCDF_CF_generic.Reader(
        settings.DRIFT_FORCING_CURRENTS_PATH,
    )
    wind_reader = reader_netCDF_CF_generic.Reader(
        settings.DRIFT_FORCING_WIND_PATH,
    )
    readers = [current_reader, wind_reader]
    if settings.DRIFT_LANDMASK_PATH:  # optional override; default auto-landmask
        readers.append(
            reader_netCDF_CF_generic.Reader(settings.DRIFT_LANDMASK_PATH))
    o.add_reader(readers)

    # ── 3. Seed from release location ────────────────────────────────
    release_time = request.release_time_utc.replace(tzinfo=None)

    o.seed_elements(
        lon=request.release_location.lon,
        lat=request.release_location.lat,
        number=settings.DRIFT_PARTICLE_COUNT,
        radius=1000,
        time=release_time,
    )

    # ── 4. Run forward ───────────────────────────────────────────────
    duration_td = timedelta(hours=duration_hours)

    duration_minutes = duration.total_seconds() / 60.0
    if duration_minutes % settings.DRIFT_OUTPUT_INTERVAL_MINUTES == 0:
        output_interval = settings.DRIFT_OUTPUT_INTERVAL_MINUTES
    else:
        output_interval = settings.DRIFT_TIMESTEP_MINUTES

    o.run(
        duration=duration_td,
        time_step=timedelta(minutes=settings.DRIFT_TIMESTEP_MINUTES),
        time_step_output=timedelta(minutes=output_interval),
    )

    # ── 5. Extract trajectory ────────────────────────────────────────
    ds = o.result
    traj_coords, traj_timestamps = _extract_trajectory_summary(ds)

    if len(traj_coords) < 2:
        raise ValueError(
            "Forward simulation produced fewer than 2 trajectory points."
        )

    # ── 6. Extract predicted footprint (convex hull at final time) ───
    predicted_footprint = None
    try:
        times = ds.time.values
        latest_time = np.max(times)
        ds_latest = ds.sel(time=latest_time)
        final_lons = ds_latest.lon.values
        final_lats = ds_latest.lat.values

        valid = ~np.isnan(final_lons) & ~np.isnan(final_lats)
        f_lons = final_lons[valid]
        f_lats = final_lats[valid]

        if len(f_lons) >= 3:
            from shapely.geometry import MultiPoint
            points = MultiPoint(
                [(float(lo), float(la)) for lo, la in zip(f_lons, f_lats)]
            )
            hull = points.convex_hull
            if hull.geom_type == "Polygon" and hull.is_valid:
                hull_dict = mapping(hull)
                predicted_footprint = GeoJSONPolygon(**hull_dict)
    except Exception as exc:
        logger.warning("Could not compute predicted footprint: %s", exc)

    # ── 7. Build response ────────────────────────────────────────────
    trajectory = GeoJSONLineString(
        type="LineString",
        coordinates=traj_coords,
    )

    return ForwardSimulationResult(
        incident_id=request.incident_id,
        vessel_mmsi=request.vessel_mmsi,
        release_location=request.release_location,
        release_time_utc=request.release_time_utc,
        trajectory=trajectory,
        trajectory_timestamps_utc=traj_timestamps,
        predicted_footprint=predicted_footprint,
        simulation_metadata=SimulationMetadata(
            particle_count=settings.DRIFT_PARTICLE_COUNT,
            duration_hours=round(duration_hours, 2),
            oil_type=settings.DRIFT_OIL_TYPE,
        ),
    )
