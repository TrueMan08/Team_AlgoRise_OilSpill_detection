"""
Request and response schemas for the attribution endpoint.

Kept in app/schemas/ (API layer) separate from app/models/ (domain layer).
Domain models in app/models/ are shared across the team and are not modified here.

This file defines:
  - AttributeRequest   : body for POST /attribute
  - CandidateReleaseState : top-ranked candidate with release state + forward payload
  - AttributeResponse  : response from POST /attribute
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.attribution import Attribution
from app.models.geometry import Point
from app.models.source_region import SourceRegion
from app.models.validation import UTCDateTime
from app.models.vessel import Vessel
from app.schemas.hindcast import ForwardSimulationRequest


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class AttributeRequest(BaseModel):
    """
    Request body for POST /api/v1/attribute.

    The caller supplies the incident identifier, the upstream source-region
    estimate (from the hindcast module), the candidate vessel list (from
    GET /vessels), and an optional spatial uncertainty radius.
    """

    incident_id: str = Field(
        ...,
        description=(
            "Unique identifier for the oil-spill incident being investigated. "
            "Matches the incident_id field in the Attribution response."
        ),
        examples=["incident-2026-001"],
    )

    source_region: SourceRegion = Field(
        ...,
        description=(
            "Hindcast-derived source region, including one or more candidate "
            "origin polygons and their release-time windows. "
            "Produced by POST /hindcast."
        ),
    )

    vessels: list[Vessel] = Field(
        ...,
        description=(
            "Candidate vessel list produced by GET /vessels. "
            "Each entry must contain at least two AIS track points."
        ),
    )

    uncertainty_radius_km: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Spatial uncertainty radius (km) from the drift module. "
            "When provided and positive, this value overrides the default "
            "10 km spatial-decay scale (λ) in the exponential proximity score. "
            "Set to None to use the default fallback."
        ),
        examples=[15.0],
    )


# ---------------------------------------------------------------------------
# Top-2 candidate with release state
# ---------------------------------------------------------------------------


class CandidateReleaseState(BaseModel):
    """
    One of the TOP 2 ranked candidate vessels with a fully resolved release
    state ready for downstream forward simulation.

    This is the primary Nimit → Ved handoff object.

    IMPORTANT: This model does NOT represent proof of responsibility.
    Scores are RELATIVE ATTRIBUTION SCORES, not probabilities of guilt.
    """

    # Ranking
    rank: int = Field(..., ge=1, description="Rank among all scored candidates (1 = highest score).")
    vessel_mmsi: str = Field(..., description="9-digit MMSI.")
    vessel_name: str | None = Field(default=None, description="Vessel name from AIS, if available.")
    vessel_type: str | None = Field(default=None, description="Vessel type from AIS, if available.")

    # Score
    overall_score: float = Field(
        ..., ge=0, le=100,
        description="Overall relative attribution score [0–100]. NOT a probability of guilt.",
    )
    confidence: str = Field(
        ...,
        description="High (≥0.70), Medium (0.40–<0.70), Low (<0.40), or no_strong_candidate.",
    )

    # Evidence summary (internal [0, 1] values for readability)
    min_distance_km: float = Field(..., ge=0, description="Minimum distance from trajectory to source polygon (km).")
    spatial_score: float = Field(..., ge=0, le=1)
    temporal_score: float = Field(..., ge=0, le=1)
    trajectory_score: float = Field(..., ge=0, le=1)
    ais_reliability_score: float = Field(..., ge=0, le=1)

    # Release state (all from actual AIS trajectory)
    release_location: Point = Field(
        ...,
        description=(
            "The selected AIS position used as the release point. "
            "Drawn from the vessel's actual observed AIS track — NOT invented."
        ),
    )
    release_time_utc: UTCDateTime = Field(
        ...,
        description="Timestamp of the selected AIS position (UTC, timezone-aware).",
    )
    observation_time_utc: UTCDateTime = Field(
        ...,
        description=(
            "Slick observation time = source_region.candidate_regions[primary].end_time_utc. "
            "Forward simulation runs from release_time_utc to this point."
        ),
    )

    # Human-readable justification
    explanation: str = Field(
        ...,
        description="Explanation of why this AIS point was selected as the release state.",
    )

    # Full attribution object (contains EvidenceBreakdown with all contributions)
    attribution: Attribution

    # Pre-built forward request, validated and ready for POST /forward
    forward_request: ForwardSimulationRequest = Field(
        ...,
        description=(
            "Validated ForwardSimulationRequest ready to be sent to POST /forward. "
            "Built from the release state above."
        ),
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class AttributeResponse(BaseModel):
    """
    Response from POST /api/v1/attribute.

    Contains:
    - all ranked Attribution objects (all vessels that passed the hard filters)
    - top_candidates: the TOP 2 ranked candidates with fully resolved release
      states and pre-built forward-simulation payloads
    - no_strong_candidate flag when the highest score is below 0.40
    """

    incident_id: str

    # All ranked attributions (full list, for Sayan's dashboard and replay)
    all_attributions: list[Attribution] = Field(
        default_factory=list,
        description=(
            "All candidates that passed the hard filters, ranked by "
            "overall attribution score descending."
        ),
    )

    # TOP 2 candidates with release states (primary Nimit → Ved handoff)
    top_candidates: list[CandidateReleaseState] = Field(
        default_factory=list,
        description=(
            "TOP 2 ranked candidates (or fewer if <2 passed the hard filters). "
            "Each contains a fully resolved release state and a pre-built "
            "ForwardSimulationRequest for POST /forward."
        ),
    )

    # Flag for downstream consumers
    no_strong_candidate: bool = Field(
        default=False,
        description=(
            "True when the highest attribution score is below 0.40. "
            "In this case, top_candidates still contains the best available "
            "candidates but should NOT be treated as confirmed suspects."
        ),
    )
