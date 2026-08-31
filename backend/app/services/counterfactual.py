"""Counterfactual evidence comparison — Ved's module.

Compares a forward simulation result (predicted trajectory + footprint)
against the observed slick to produce geometric plausibility evidence.

SCIENTIFIC HONESTY NOTE:
    The metrics here are GEOMETRIC OVERLAP INDICATORS, not posterior
    probabilities of responsibility.  A Jaccard index of 0.5 means
    50% geometric overlap between the predicted and observed polygons;
    it does NOT mean a 50% chance the vessel caused the spill.

Reuses the UTM projection helpers from ``app.services.attribution``
to compute metric distances (km).
"""

from __future__ import annotations

import logging

from shapely.geometry import LineString as ShapelyLineString
from shapely.geometry import Polygon as ShapelyPolygon

from app.schemas.counterfactual import CounterfactualRequest, CounterfactualResult
from app.services.attribution import (
    _geojson_to_shapely,
    _get_utm_epsg,
    _project,
)

logger = logging.getLogger("oilspill_backend.counterfactual")


def run_counterfactual(request: CounterfactualRequest) -> CounterfactualResult:
    """Compare a forward simulation against the observed slick.

    Metrics
    -------
    spatial_agreement
        Jaccard index: intersection_area / union_area of the predicted
        footprint and the observed slick polygon.  Computed in a local
        UTM projection for metric accuracy.
    trajectory_reaches_slick
        Boolean: does the forward trajectory LineString intersect the
        observed slick polygon?
    centroid_distance_km
        Metric distance (km) between the centroids of the predicted
        footprint and the observed slick.

    When the forward simulation produces no footprint (e.g. too few
    particles), spatial_agreement = 0.0 and the centroid distance is
    computed from the trajectory endpoint instead.
    """
    fwd = request.forward_result
    slick = request.observed_slick

    # ── Convert observed slick geometry to Shapely ────────────────────
    observed_poly = _geojson_to_shapely(slick.geometry)
    if not observed_poly.is_valid:
        observed_poly = observed_poly.buffer(0)

    obs_centroid = observed_poly.centroid
    utm_epsg = _get_utm_epsg(obs_centroid.x, obs_centroid.y)

    # ── Trajectory → Shapely LineString ──────────────────────────────
    traj_coords = fwd.trajectory.coordinates
    traj_line = ShapelyLineString([(c[0], c[1]) for c in traj_coords])

    trajectory_reaches_slick = traj_line.intersects(observed_poly)

    # ── Predicted footprint comparison ───────────────────────────────
    if fwd.predicted_footprint is not None:
        predicted_poly = _geojson_to_shapely(fwd.predicted_footprint)
        if not predicted_poly.is_valid:
            predicted_poly = predicted_poly.buffer(0)

        # Project both to UTM for metric-accurate area comparison.
        obs_proj = _project(observed_poly, utm_epsg)
        pred_proj = _project(predicted_poly, utm_epsg)

        intersection_area = obs_proj.intersection(pred_proj).area
        union_area = obs_proj.union(pred_proj).area

        if union_area > 0:
            spatial_agreement = intersection_area / union_area
        else:
            spatial_agreement = 0.0

        # Centroid distance in km.
        pred_centroid_proj = _project(predicted_poly.centroid, utm_epsg)
        obs_centroid_proj = _project(obs_centroid, utm_epsg)
        centroid_distance_km = pred_centroid_proj.distance(obs_centroid_proj) / 1000.0
    else:
        # No footprint available — fall back to trajectory endpoint.
        spatial_agreement = 0.0

        # Use the last trajectory point as the best available estimate.
        last_coord = traj_coords[-1]
        from shapely.geometry import Point as ShapelyPoint
        last_pt = ShapelyPoint(last_coord[0], last_coord[1])

        last_pt_proj = _project(last_pt, utm_epsg)
        obs_centroid_proj = _project(obs_centroid, utm_epsg)
        centroid_distance_km = last_pt_proj.distance(obs_centroid_proj) / 1000.0

    # ── Evidence strength label ──────────────────────────────────────
    if spatial_agreement >= 0.3:
        evidence_strength = "Strong"
    elif spatial_agreement >= 0.1:
        evidence_strength = "Moderate"
    elif spatial_agreement > 0.0:
        evidence_strength = "Weak"
    else:
        evidence_strength = "None"

    # ── Human-readable explanation ───────────────────────────────────
    parts: list[str] = []

    if fwd.predicted_footprint is not None:
        parts.append(
            f"Predicted footprint overlaps {spatial_agreement:.1%} "
            f"(Jaccard index) with the observed slick."
        )
    else:
        parts.append(
            "No predicted footprint was produced (insufficient "
            "particle spread); spatial agreement cannot be computed."
        )

    if trajectory_reaches_slick:
        parts.append(
            "The simulated trajectory intersects the observed slick polygon."
        )
    else:
        parts.append(
            "The simulated trajectory does NOT intersect the observed slick polygon."
        )

    parts.append(
        f"Centroid distance: {centroid_distance_km:.2f} km."
    )

    parts.append(
        f"Evidence strength: {evidence_strength}. "
        "This is a geometric consistency indicator, NOT proof of responsibility."
    )

    explanation = " ".join(parts)

    logger.info(
        "Counterfactual comparison: vessel=%s, spatial=%.4f, "
        "traj_reaches=%s, dist=%.2f km, strength=%s",
        request.vessel_mmsi,
        spatial_agreement,
        trajectory_reaches_slick,
        centroid_distance_km,
        evidence_strength,
    )

    return CounterfactualResult(
        incident_id=request.incident_id,
        vessel_mmsi=request.vessel_mmsi,
        spatial_agreement=round(spatial_agreement, 6),
        trajectory_reaches_slick=trajectory_reaches_slick,
        centroid_distance_km=round(centroid_distance_km, 4),
        evidence_strength=evidence_strength,
        explanation=explanation,
        predicted_footprint=fwd.predicted_footprint,
        observed_slick_geometry=slick.geometry,
    )
