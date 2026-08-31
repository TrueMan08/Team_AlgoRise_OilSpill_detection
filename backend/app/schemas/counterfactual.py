"""Request and response schemas for counterfactual evidence comparison.

Compares a forward simulation result (predicted trajectory and footprint)
against the observed slick to assess physical plausibility.

IMPORTANT: Agreement metrics are GEOMETRIC OVERLAP INDICATORS, not
posterior probabilities.  A high spatial_agreement means the predicted
oil footprint has high geometric overlap with the observed slick; it does
NOT mean the candidate is confirmed responsible.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.geometry import GeoJSONGeometry, GeoJSONLineString, Point
from app.models.slick import Slick
from app.models.validation import UTCDateTime
from app.schemas.hindcast import ForwardSimulationResult


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class CounterfactualRequest(BaseModel):
    """Input for ``POST /counterfactual``.

    Caller supplies the forward simulation result (from ``POST /forward``)
    and the originally detected slick (from ``POST /detect`` or the
    ``HindcastRequest.slick``).
    """

    incident_id: str
    vessel_mmsi: str = Field(..., min_length=9, max_length=9)
    forward_result: ForwardSimulationResult
    observed_slick: Slick


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class CounterfactualResult(BaseModel):
    """Output of ``POST /counterfactual``.

    Provides geometric evidence for physical plausibility assessment.

    IMPORTANT — INTERPRETATION GUIDANCE
    ====================================
    ``spatial_agreement`` is a normalised geometric overlap (Jaccard index
    of footprint ∩ slick / footprint ∪ slick).  It ranges from 0.0 (no
    overlap) to 1.0 (identical geometries).  This is a geometric indicator
    of consistency, NOT a probability that the vessel is responsible.

    ``trajectory_reaches_slick`` is a binary indicator of whether any
    point on the simulated trajectory intersects or enters the observed
    slick polygon.

    ``centroid_distance_km`` is the metric distance between the centre
    of the predicted footprint and the centre of the observed slick.
    A small distance suggests the simulation drifted toward the
    observation location.
    """

    incident_id: str
    vessel_mmsi: str

    # ── Geometric agreement metrics ──────────────────────────────────

    spatial_agreement: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Jaccard index (intersection area / union area) of the "
            "predicted footprint and the observed slick polygon.  "
            "0.0 = no overlap, 1.0 = identical.  "
            "This is a geometric overlap indicator, NOT a probability."
        ),
    )

    trajectory_reaches_slick: bool = Field(
        ...,
        description=(
            "True if the predicted forward trajectory LineString "
            "intersects the observed slick polygon."
        ),
    )

    centroid_distance_km: float = Field(
        ...,
        ge=0.0,
        description=(
            "Metric distance (km) between the centroid of the "
            "predicted footprint and the centroid of the observed "
            "slick geometry."
        ),
    )

    # ── Context ──────────────────────────────────────────────────────

    evidence_strength: Literal["Strong", "Moderate", "Weak", "None"] = Field(
        ...,
        description=(
            "Qualitative label derived from spatial_agreement.  "
            "Strong ≥ 0.3, Moderate ≥ 0.1, Weak > 0, None = 0.  "
            "These thresholds are heuristic and should NOT be "
            "interpreted as legal evidence standards."
        ),
    )

    explanation: str = Field(
        ...,
        description=(
            "Human-readable summary of the counterfactual comparison."
        ),
    )

    # ── Geometries (for frontend rendering) ──────────────────────────

    predicted_footprint: GeoJSONGeometry | None = Field(
        default=None,
        description="The forward simulation's predicted oil footprint.",
    )

    observed_slick_geometry: GeoJSONGeometry = Field(
        ...,
        description="The observed slick polygon.",
    )
