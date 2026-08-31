"""
AIS vessel attribution scoring engine — Nimit's module.

Score formula (frozen MVP):
    Score(v) = 0.35 × Spatial + 0.30 × Temporal + 0.20 × Trajectory
               + 0.15 × AIS_Reliability

Components are computed in [0, 1] and converted to the [0, 100] scale
required by the EvidenceScore Pydantic model.

Evidence-breakdown mapping (Option A — no shared model changes):
    EvidenceBreakdown.spatial            → Spatial proximity score     (w=0.35)
    EvidenceBreakdown.temporal           → Temporal compatibility score (w=0.30)
    EvidenceBreakdown.trajectory         → Trajectory intersection      (w=0.20)
    EvidenceBreakdown.source_probability → AIS Reliability heuristic    (w=0.15)
    EvidenceBreakdown.ais_anomaly        → Zero slot; ML deferred        (w=0.00)

Weight sum: 0.35 + 0.30 + 0.20 + 0.15 + 0.00 = 1.00  ✓

Hard filters:
    - Spatial:   vessels > 150 km from source polygon   → excluded.
    - Temporal:  no AIS within ±12 h of release window  → excluded.
    - Segment:   < 3 track points per segment           → segment discarded.
    - Gap split: consecutive observations > 30 min      → new segment.

Release-state selection (polygon-distance rule, not centroid):
    A. Valid points: timestamp <= observation_time_utc.
    B. Prefer points inside the release window.
    C. Inside window → pick the point closest to the SOURCE POLYGON.
    D. No inside-window points → temporally nearest in ±12 h window;
       polygon distance used as tie-breaker.
    E-H. release_location/release_time_utc from the selected AIS point;
         validate release_time_utc <= observation_time_utc.

Language discipline:
    - Scores are RELATIVE ATTRIBUTION SCORES, not probabilities.
    - Candidates are "suspects" / "candidates", never "culprits".
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import exp
from typing import TYPE_CHECKING

from pyproj import Transformer
from shapely.geometry import LineString as ShapelyLineString
from shapely.geometry import MultiPolygon as ShapelyMultiPolygon
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import transform as shapely_transform

from app.models.attribution import (
    Attribution,
    EvidenceBreakdown,
    EvidenceScore,
    SourceRegionMatch,
)
from app.models.geometry import Point
from app.models.source_candidate_region import SourceCandidateRegion
from app.models.source_region import SourceRegion
from app.models.vessel import Vessel
from app.schemas.hindcast import ForwardSimulationRequest

if TYPE_CHECKING:
    from app.schemas.attribution import AttributeResponse, CandidateReleaseState


# ---------------------------------------------------------------------------
# Frozen scoring constants
# ---------------------------------------------------------------------------

_WEIGHT_SPATIAL: float = 0.35
_WEIGHT_TEMPORAL: float = 0.30
_WEIGHT_TRAJECTORY: float = 0.20
_WEIGHT_AIS_RELIABILITY: float = 0.15
_WEIGHT_AIS_ANOMALY: float = 0.00  # zero slot; behavioural ML deferred

_SPATIAL_HARD_LIMIT_KM: float = 150.0
_TEMPORAL_HARD_HOURS: float = 12.0
_TAU_HOURS: float = 2.0            # temporal Gaussian decay half-width
_LAMBDA_FALLBACK_KM: float = 10.0  # spatial decay scale (λ) fallback
_GAP_THRESHOLD_MIN: int = 30       # AIS gap threshold for segment splitting
_MIN_SEGMENT_POINTS: int = 3       # minimum points to keep a segment


# ---------------------------------------------------------------------------
# Geospatial helpers
# ---------------------------------------------------------------------------

def _get_utm_epsg(lon: float, lat: float) -> str:
    """Return the EPSG code for the UTM zone covering (lon, lat)."""
    zone = int((lon + 180.0) / 6.0) + 1
    hemisphere_offset = 32600 if lat >= 0 else 32700
    return f"EPSG:{hemisphere_offset + zone}"


def _project(geometry, target_epsg: str):
    """Project a Shapely geometry from WGS84 to the given CRS (always_xy=True)."""
    transformer = Transformer.from_crs("EPSG:4326", target_epsg, always_xy=True)
    return shapely_transform(transformer.transform, geometry)


def _min_distance_km(trajectory: ShapelyLineString, source_polygon) -> float:
    """
    Minimum metric distance (km) from a trajectory to the source polygon.

    The source polygon centroid is used ONLY to pick a local UTM zone.
    The distance is measured between the projected geometries — never
    centroid-to-centroid.
    """
    centroid = source_polygon.centroid
    utm = _get_utm_epsg(centroid.x, centroid.y)
    return _project(trajectory, utm).distance(_project(source_polygon, utm)) / 1000.0


def _point_distance_to_polygon_km(point: ShapelyPoint, source_polygon) -> float:
    """Minimum metric distance (km) from a single point to the source polygon."""
    centroid = source_polygon.centroid
    utm = _get_utm_epsg(centroid.x, centroid.y)
    return _project(point, utm).distance(_project(source_polygon, utm)) / 1000.0


def _geojson_to_shapely(geometry) -> ShapelyPolygon | ShapelyMultiPolygon:
    """Convert a GeoJSONPolygon or GeoJSONMultiPolygon to a Shapely geometry."""
    if geometry.type == "Polygon":
        exterior = [(c[0], c[1]) for c in geometry.coordinates[0]]
        holes = [[(c[0], c[1]) for c in ring] for ring in geometry.coordinates[1:]]
        return ShapelyPolygon(exterior, holes)
    polys = []
    for poly_coords in geometry.coordinates:
        exterior = [(c[0], c[1]) for c in poly_coords[0]]
        holes = [[(c[0], c[1]) for c in ring] for ring in poly_coords[1:]]
        polys.append(ShapelyPolygon(exterior, holes))
    return ShapelyMultiPolygon(polys)


# ---------------------------------------------------------------------------
# Trajectory reconstruction
# ---------------------------------------------------------------------------

def _reconstruct_segments(
    vessel: Vessel,
    source_polygon,
    gap_threshold_min: int = _GAP_THRESHOLD_MIN,
    min_points: int = _MIN_SEGMENT_POINTS,
) -> list[dict]:
    """
    Split a vessel's track into continuous segments.

    Splits at gaps > gap_threshold_min minutes; drops segments with
    fewer than min_points observations.

    Returns a list of segment dicts:
        {
          "geometry":        ShapelyLineString (WGS84, lon/lat),
          "min_distance_km": float,
          "timestamps":      list[datetime],
          "track_points":    list[VesselTrackPoint],
        }
    """
    points = vessel.track_points
    if len(points) < min_points:
        return []

    raw_segments: list[list] = []
    current: list = [points[0]]
    for i in range(1, len(points)):
        gap_min = (points[i].timestamp_utc - points[i - 1].timestamp_utc).total_seconds() / 60.0
        if gap_min > gap_threshold_min:
            if len(current) >= min_points:
                raw_segments.append(current)
            current = [points[i]]
        else:
            current.append(points[i])
    if len(current) >= min_points:
        raw_segments.append(current)

    result: list[dict] = []
    for seg_pts in raw_segments:
        geom = ShapelyLineString([(p.position.lon, p.position.lat) for p in seg_pts])
        result.append({
            "geometry": geom,
            "min_distance_km": _min_distance_km(geom, source_polygon),
            "timestamps": [p.timestamp_utc for p in seg_pts],
            "track_points": seg_pts,
        })
    return result


# ---------------------------------------------------------------------------
# Individual score functions (internal [0, 1])
# ---------------------------------------------------------------------------

def compute_spatial_score(distance_km: float, lambda_km: float) -> float:
    """
    Exponential proximity score: exp(-distance_km / lambda_km).

    Returns 1.0 when the trajectory touches the polygon (distance = 0).
    """
    return float(exp(-distance_km / lambda_km))


def compute_temporal_score(
    timestamps: list[datetime],
    window_start: datetime,
    window_end: datetime,
    tau_hours: float = _TAU_HOURS,
) -> float:
    """
    Temporal compatibility score.

    Returns 1.0 if any timestamp falls inside [window_start, window_end].
    Outside the window, applies Gaussian decay: exp(-(Δh²) / (2τ²)).
    Returns the maximum score across all timestamps.
    """
    best = 0.0
    for ts in timestamps:
        if window_start <= ts <= window_end:
            return 1.0
        delta_h = (
            (window_start - ts).total_seconds() / 3600.0 if ts < window_start
            else (ts - window_end).total_seconds() / 3600.0
        )
        score = exp(-(delta_h ** 2) / (2.0 * tau_hours ** 2))
        if score > best:
            best = score
    return float(best)


def compute_trajectory_score(segments: list[dict], source_polygon) -> float:
    """
    Binary trajectory intersection score.

    Returns 1.0 if any segment intersects the source polygon, 0.0 otherwise.
    """
    return 1.0 if any(s["geometry"].intersects(source_polygon) for s in segments) else 0.0


def compute_ais_reliability(
    timestamps: list[datetime],
    window_start: datetime,
    window_end: datetime,
) -> float:
    """
    AIS data-quality heuristic (MVP, not a calibrated probability).

        reliability = coverage × (1 - 0.5 × gap_penalty)

    where:
        coverage    = observed_hourly_bins / total_window_hours  (clamped [0, 1])
        gap_penalty = min(1.0, max_gap_minutes / 60)

    Returns 0.0 when no AIS timestamps fall within the release window.

    Note: An AIS gap is missing evidence, NOT proof of absence.
    """
    relevant = sorted(t for t in timestamps if window_start <= t <= window_end)
    if not relevant:
        return 0.0

    window_hours = max(1, int((window_end - window_start).total_seconds() / 3600.0))
    observed_hours = {t.replace(minute=0, second=0, microsecond=0) for t in relevant}
    coverage = min(1.0, len(observed_hours) / window_hours)

    max_gap_min = max(
        ((b - a).total_seconds() / 60.0 for a, b in zip(relevant[:-1], relevant[1:])),
        default=0.0,
    )
    gap_penalty = min(1.0, max_gap_min / 60.0)
    return float(max(0.0, min(1.0, coverage * (1.0 - 0.5 * gap_penalty))))


# ---------------------------------------------------------------------------
# Evidence score construction helper
# ---------------------------------------------------------------------------

def _make_evidence_score(score_01: float, weight: float, explanation: str) -> EvidenceScore:
    """
    Convert an internal [0, 1] score to [0, 100] and build an EvidenceScore.

    contribution is computed from the same score_100 value so the Pydantic
    contribution == score × weight validator always passes exactly.
    """
    score_100 = score_01 * 100.0
    return EvidenceScore(
        score=score_100,
        weight=weight,
        contribution=score_100 * weight,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Core vessel scoring (private helper — single source of truth)
# ---------------------------------------------------------------------------

def _score_vessels(
    vessels: list[Vessel],
    source_region: SourceRegion,
    lambda_km: float,
) -> list[dict]:
    """
    Apply hard filters, compute evidence scores, and return scored vessel dicts.

    Each dict contains the raw [0, 1] scores, the Attribution-compatible
    EvidenceBreakdown, and the pre-built SourceRegionMatch list.

    Returns a list sorted by total_01 descending (rank 1 first).
    """
    primary = max(source_region.candidate_regions, key=lambda c: c.probability)
    source_polygon = _geojson_to_shapely(primary.geometry)
    window_start = primary.start_time_utc
    window_end = primary.end_time_utc

    candidate_polygons = {
        cand.id: _geojson_to_shapely(cand.geometry)
        for cand in source_region.candidate_regions
    }

    hard_time_start = window_start - timedelta(hours=_TEMPORAL_HARD_HOURS)
    hard_time_end = window_end + timedelta(hours=_TEMPORAL_HARD_HOURS)

    scored: list[dict] = []

    for vessel in vessels:
        segments = _reconstruct_segments(vessel, source_polygon)
        if not segments:
            continue

        all_timestamps = [ts for seg in segments for ts in seg["timestamps"]]

        if not any(hard_time_start <= ts <= hard_time_end for ts in all_timestamps):
            continue

        min_dist_km = min(seg["min_distance_km"] for seg in segments)
        if min_dist_km > _SPATIAL_HARD_LIMIT_KM:
            continue

        spatial_01 = compute_spatial_score(min_dist_km, lambda_km)
        temporal_01 = compute_temporal_score(all_timestamps, window_start, window_end)
        trajectory_01 = compute_trajectory_score(segments, source_polygon)
        ais_rel_01 = compute_ais_reliability(all_timestamps, window_start, window_end)

        total_01 = max(0.0, min(1.0,
            _WEIGHT_SPATIAL * spatial_01
            + _WEIGHT_TEMPORAL * temporal_01
            + _WEIGHT_TRAJECTORY * trajectory_01
            + _WEIGHT_AIS_RELIABILITY * ais_rel_01
        ))

        if total_01 >= 0.70:
            label = "High"
        elif total_01 >= 0.40:
            label = "Medium"
        else:
            label = "Low"

        spatial_es = _make_evidence_score(
            spatial_01, _WEIGHT_SPATIAL,
            f"[{label}] Minimum distance to source region: {min_dist_km:.2f} km. "
            f"Relative spatial score: {spatial_01:.4f}.",
        )
        temporal_es = _make_evidence_score(
            temporal_01, _WEIGHT_TEMPORAL,
            (
                "AIS timestamp observed inside release window "
                f"[{window_start.strftime('%Y-%m-%dT%H:%MZ')} – "
                f"{window_end.strftime('%Y-%m-%dT%H:%MZ')}]."
            ) if temporal_01 == 1.0 else (
                f"No AIS timestamp inside release window. "
                f"Gaussian decay score: {temporal_01:.4f} (τ={_TAU_HOURS} h)."
            ),
        )
        trajectory_es = _make_evidence_score(
            trajectory_01, _WEIGHT_TRAJECTORY,
            "At least one reconstructed trajectory segment intersects the source polygon."
            if trajectory_01 == 1.0
            else "No reconstructed trajectory segment intersects the source polygon.",
        )
        # source_probability slot carries AIS Reliability (Option A mapping).
        ais_rel_es = _make_evidence_score(
            ais_rel_01, _WEIGHT_AIS_RELIABILITY,
            f"AIS data reliability (proposed MVP heuristic): {ais_rel_01:.4f}. "
            "Measures hourly-bin coverage with a gap penalty. "
            "This is NOT a calibrated probability; treat as a data-quality indicator.",
        )
        # ais_anomaly slot is zero — behavioural ML deferred from MVP.
        ais_anomaly_es = EvidenceScore(
            score=0.0, weight=_WEIGHT_AIS_ANOMALY, contribution=0.0,
            explanation="Behavioural anomaly detection is deferred from the MVP. Score=0, weight=0.",
        )

        breakdown = EvidenceBreakdown(
            spatial=spatial_es, temporal=temporal_es, trajectory=trajectory_es,
            source_probability=ais_rel_es, ais_anomaly=ais_anomaly_es,
        )
        overall_100 = (
            spatial_es.contribution + temporal_es.contribution
            + trajectory_es.contribution + ais_rel_es.contribution
            + ais_anomaly_es.contribution
        )

        matched_regions: list[SourceRegionMatch] = []
        seen_cand_ids: set[str] = set()
        for cand in source_region.candidate_regions:
            if cand.id in seen_cand_ids:
                continue
            seen_cand_ids.add(cand.id)
            cand_poly = candidate_polygons[cand.id]
            traj_intersects = any(s["geometry"].intersects(cand_poly) for s in segments)
            compat = float(cand.probability) if traj_intersects else 0.0
            matched_regions.append(SourceRegionMatch(
                source_candidate_region_id=cand.id,
                compatibility_score=max(0.0, min(1.0, compat)),
            ))

        scored.append({
            "vessel": vessel,
            "mmsi": vessel.mmsi,
            "total_01": total_01,
            "overall_100": overall_100,
            "breakdown": breakdown,
            "matched_regions": matched_regions,
            "min_dist_km": min_dist_km,
            "spatial_01": spatial_01,
            "temporal_01": temporal_01,
            "trajectory_01": trajectory_01,
            "ais_rel_01": ais_rel_01,
            "confidence": label,
        })

    scored.sort(key=lambda x: x["total_01"], reverse=True)
    return scored


def _lambda_from(uncertainty_radius_km: float | None) -> float:
    """Return the spatial decay scale λ (km)."""
    return (
        uncertainty_radius_km
        if (uncertainty_radius_km is not None and uncertainty_radius_km > 0)
        else _LAMBDA_FALLBACK_KM
    )


# ---------------------------------------------------------------------------
# Public: attribution-only (returns ranked Attribution list)
# ---------------------------------------------------------------------------

def run_attribution(
    incident_id: str,
    source_region: SourceRegion,
    vessels: list[Vessel],
    uncertainty_radius_km: float | None = None,
) -> list[Attribution]:
    """
    Score and rank candidate vessels against a hindcast source region.

    Algorithm (frozen MVP):
        1. Select the primary candidate region (highest probability).
        2. For each vessel: hard-filter → score four components → weighted sum.
        3. Sort by total score descending; assign ranks 1…N.

    Score interpretation:
        Scores are RELATIVE ATTRIBUTION SCORES, not posterior probabilities.
        A score of 0.82 (82.0/100) means the vessel ranks highly under the
        project's evidence heuristic; it does NOT mean 82% probability of guilt.
        When the highest score is below 0.40, treat as "no strong candidate".

    Returns:
        List of Attribution objects ranked by overall_score descending.
        Returns an empty list when no vessel passes the hard filters.
    """
    scored = _score_vessels(vessels, source_region, _lambda_from(uncertainty_radius_km))
    return [
        Attribution(
            incident_id=incident_id,
            mmsi=entry["mmsi"],
            overall_score=entry["overall_100"],
            rank=rank,
            evidence_breakdown=entry["breakdown"],
            matched_source_regions=entry["matched_regions"],
        )
        for rank, entry in enumerate(scored, start=1)
    ]


# ---------------------------------------------------------------------------
# Release-state selection (polygon-distance rule, not centroid)
# ---------------------------------------------------------------------------

def select_release_state(
    vessel: Vessel,
    primary: SourceCandidateRegion,
    source_polygon,
) -> tuple[Point, datetime, datetime, str]:
    """
    Select the best AIS track point to use as the release state for /forward.

    Rule:
    A. Valid points: timestamp <= observation_time_utc.
    B. Prefer points inside the release window [start_time_utc, end_time_utc].
    C. Inside window → pick the point closest to the SOURCE POLYGON.
    D. No inside-window points → temporally nearest in ±12 h window;
       polygon distance used as tie-breaker.
    E. release_location = selected AIS point position (real coordinate).
    F. release_time_utc = selected AIS point timestamp (real timestamp).
    G. observation_time_utc = primary.end_time_utc.
    H. Validates release_time_utc <= observation_time_utc.

    Returns:
        (release_location, release_time_utc, observation_time_utc, explanation)
    """
    observation_time_utc = primary.end_time_utc
    window_start = primary.start_time_utc
    window_end = primary.end_time_utc
    hard_window_start = window_start - timedelta(hours=_TEMPORAL_HARD_HOURS)

    valid_points = [p for p in vessel.track_points if p.timestamp_utc <= observation_time_utc]
    if not valid_points:
        pt = vessel.track_points[0]
        return (
            pt.position, pt.timestamp_utc, observation_time_utc,
            f"Fallback: no valid AIS point at or before observation time. "
            f"Selected earliest observed position at {pt.timestamp_utc.isoformat()}.",
        )

    def poly_dist_km(pt) -> float:
        return _point_distance_to_polygon_km(
            ShapelyPoint(pt.position.lon, pt.position.lat), source_polygon
        )

    inside_window = [p for p in valid_points if window_start <= p.timestamp_utc <= window_end]

    if inside_window:
        best = min(inside_window, key=poly_dist_km)
        explanation = (
            f"Selected AIS position at {best.timestamp_utc.isoformat()} "
            f"because it was inside the release window and closest to the "
            f"source polygon ({poly_dist_km(best):.2f} km)."
        )
    else:
        candidates = [p for p in valid_points if p.timestamp_utc >= hard_window_start] or valid_points

        def time_dist_to_window(pt) -> float:
            ts = pt.timestamp_utc
            if ts < window_start:
                return (window_start - ts).total_seconds()
            if ts > window_end:
                return (ts - window_end).total_seconds()
            return 0.0

        best = min(candidates, key=lambda p: (time_dist_to_window(p), poly_dist_km(p)))
        explanation = (
            f"Selected AIS position at {best.timestamp_utc.isoformat()} "
            f"as the temporally closest observed position to the release window "
            f"outside the window, with {poly_dist_km(best):.2f} km distance to "
            f"source polygon (used as tie-breaker)."
        )

    release_time = best.timestamp_utc
    if release_time > observation_time_utc:
        release_time = observation_time_utc
        explanation += " [Clamped to observation_time_utc for safety.]"

    return best.position, release_time, observation_time_utc, explanation


# ---------------------------------------------------------------------------
# Build TOP 2 candidates with release states
# ---------------------------------------------------------------------------

def build_top_candidates(
    attributions: list[Attribution],
    scored_details: list[dict],
    vessels: list[Vessel],
    source_region: SourceRegion,
    incident_id: str,
    top_n: int = 2,
) -> "list[CandidateReleaseState]":
    """
    Build the TOP top_n ranked candidates with release states and forward requests.

    This is the primary Nimit → Ved integration output.

    Args:
        attributions:   Ranked Attribution list from run_attribution().
        scored_details: Internal scored dicts (vessel objects + raw scores).
        vessels:        Original vessel list (for MMSI → Vessel lookup).
        source_region:  The hindcast source region.
        incident_id:    Incident identifier.
        top_n:          Maximum number of candidates to return (default 2).

    Returns:
        List of CandidateReleaseState (≤ top_n entries). Fewer than top_n
        when fewer candidates passed the hard filters.
    """
    from app.schemas.attribution import CandidateReleaseState  # avoid circular import

    primary = max(source_region.candidate_regions, key=lambda c: c.probability)
    source_polygon = _geojson_to_shapely(primary.geometry)
    vessel_by_mmsi: dict[str, Vessel] = {v.mmsi: v for v in vessels}
    details_by_mmsi: dict[str, dict] = {d["mmsi"]: d for d in scored_details}

    result: list[CandidateReleaseState] = []
    for attr in attributions[:top_n]:
        vessel = vessel_by_mmsi.get(attr.mmsi)
        details = details_by_mmsi.get(attr.mmsi)
        if vessel is None or details is None:
            continue

        release_location, release_time_utc, observation_time_utc, explanation = (
            select_release_state(vessel, primary, source_polygon)
        )
        forward_request = ForwardSimulationRequest(
            incident_id=incident_id,
            vessel_mmsi=attr.mmsi,
            release_location=release_location,
            release_time_utc=release_time_utc,
            observation_time_utc=observation_time_utc,
        )
        result.append(CandidateReleaseState(
            rank=attr.rank,
            vessel_mmsi=attr.mmsi,
            vessel_name=vessel.name,
            vessel_type=vessel.vessel_type,
            overall_score=attr.overall_score,
            confidence=details["confidence"],
            min_distance_km=details["min_dist_km"],
            spatial_score=details["spatial_01"],
            temporal_score=details["temporal_01"],
            trajectory_score=details["trajectory_01"],
            ais_reliability_score=details["ais_rel_01"],
            release_location=release_location,
            release_time_utc=release_time_utc,
            observation_time_utc=observation_time_utc,
            explanation=explanation,
            attribution=attr,
            forward_request=forward_request,
        ))

    return result


# ---------------------------------------------------------------------------
# Public: full pipeline (attribution + TOP 2 + release states)
# ---------------------------------------------------------------------------

def run_full_attribution(
    incident_id: str,
    source_region: SourceRegion,
    vessels: list[Vessel],
    uncertainty_radius_km: float | None = None,
) -> "AttributeResponse":
    """
    Run the complete Nimit attribution pipeline and return an AttributeResponse.

    Scores all candidate vessels, ranks them, selects the TOP 2, and for each
    builds a release state (from real AIS data) and a pre-validated
    ForwardSimulationRequest for POST /forward.

    Returns:
        AttributeResponse with:
          - all_attributions:    full ranked list (all that passed hard filters)
          - top_candidates:      TOP 2 with release states and forward payloads
          - no_strong_candidate: True when highest score < 0.40
    """
    from app.schemas.attribution import AttributeResponse  # avoid circular import

    scored = _score_vessels(vessels, source_region, _lambda_from(uncertainty_radius_km))
    no_strong = not scored or scored[0]["total_01"] < 0.40

    attributions: list[Attribution] = [
        Attribution(
            incident_id=incident_id,
            mmsi=entry["mmsi"],
            overall_score=entry["overall_100"],
            rank=rank,
            evidence_breakdown=entry["breakdown"],
            matched_source_regions=entry["matched_regions"],
        )
        for rank, entry in enumerate(scored, start=1)
    ]

    top_candidates = build_top_candidates(
        attributions=attributions,
        scored_details=scored,
        vessels=vessels,
        source_region=source_region,
        incident_id=incident_id,
        top_n=2,
    )

    return AttributeResponse(
        incident_id=incident_id,
        all_attributions=attributions,
        top_candidates=top_candidates,
        no_strong_candidate=no_strong,
    )
