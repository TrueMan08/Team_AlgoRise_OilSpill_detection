"""Request and response schemas for drift simulation endpoints.

These are API-layer contracts (request validation / response serialization),
not domain models.  Domain entities live in ``app/models/``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.geometry import GeoJSONGeometry, GeoJSONLineString, Point
from app.models.slick import Slick
from app.models.source_region import SourceRegion
from app.models.validation import UTCDateTime


# ---------------------------------------------------------------------------
# Backward hindcast
# ---------------------------------------------------------------------------


class HindcastRequest(BaseModel):
    """Input for ``POST /hindcast``.

    The caller supplies the detected ``Slick`` and an optional override
    for how far back to simulate.
    """

    slick: Slick
    duration_hours: int = Field(
        default=12,
        gt=0,
        le=72,
        description=(
            "How many hours to trace particles backward from "
            "the slick observation time."
        ),
    )


class HindcastResponse(BaseModel):
    """Output of ``POST /hindcast``.

    Wraps the domain ``SourceRegion`` with a lightweight trajectory
    summary suitable for frontend display and Nimit's AIS filtering.
    """

    source_region: SourceRegion

    backward_trajectory: GeoJSONLineString = Field(
        ...,
        description=(
            "Mean/centroid path of backward-drifting particles, "
            "GeoJSON [longitude, latitude] coordinate order."
        ),
    )

    trajectory_timestamps_utc: list[UTCDateTime] = Field(
        ...,
        min_length=2,
        description=(
            "UTC timestamps with a strict 1:1 index mapping to "
            "backward_trajectory.coordinates.  The first entry is "
            "the slick observation time; the last is the earliest "
            "reconstruction time."
        ),
    )

    @model_validator(mode="after")
    def validate_trajectory_timestamp_alignment(self):
        n_coords = len(self.backward_trajectory.coordinates)
        n_times = len(self.trajectory_timestamps_utc)
        if n_coords != n_times:
            raise ValueError(
                f"backward_trajectory has {n_coords} coordinates but "
                f"trajectory_timestamps_utc has {n_times} entries; "
                f"they must have a strict 1:1 mapping."
            )
        return self


# ---------------------------------------------------------------------------
# Forward counterfactual simulation
# ---------------------------------------------------------------------------


class SimulationMetadata(BaseModel):
    """Non-scientific bookkeeping returned alongside a simulation result."""

    particle_count: int = Field(..., gt=0)
    duration_hours: float = Field(..., gt=0)
    oil_type: str


class ForwardSimulationRequest(BaseModel):
    """Input for ``POST /forward``.

    Nimit supplies the candidate release state after attribution.
    Ved's forward simulation checks physical plausibility.
    """

    incident_id: str
    vessel_mmsi: str = Field(..., min_length=9, max_length=9)

    release_location: Point
    release_time_utc: UTCDateTime

    observation_time_utc: UTCDateTime = Field(
        ...,
        description=(
            "The slick observation time.  The forward simulation "
            "runs from release_time_utc up to this point."
        ),
    )

    @model_validator(mode="after")
    def validate_release_before_observation(self):
        if self.release_time_utc > self.observation_time_utc:
            raise ValueError(
                "release_time_utc must be <= observation_time_utc "
                "(cannot release oil after it was observed)."
            )
        return self


class ForwardSimulationResult(BaseModel):
    """Output of ``POST /forward``."""

    incident_id: str
    vessel_mmsi: str

    release_location: Point
    release_time_utc: UTCDateTime

    trajectory: GeoJSONLineString = Field(
        ...,
        description=(
            "Centroid path of forward-drifting particles, "
            "GeoJSON [longitude, latitude] coordinate order."
        ),
    )

    trajectory_timestamps_utc: list[UTCDateTime] = Field(
        ...,
        min_length=2,
        description=(
            "UTC timestamps with a strict 1:1 index mapping to "
            "trajectory.coordinates."
        ),
    )

    predicted_footprint: GeoJSONGeometry | None = Field(
        default=None,
        description=(
            "Convex hull of the final particle cloud at the "
            "observation time, or null if unavailable."
        ),
    )

    simulation_metadata: SimulationMetadata

    @model_validator(mode="after")
    def validate_trajectory_timestamp_alignment(self):
        n_coords = len(self.trajectory.coordinates)
        n_times = len(self.trajectory_timestamps_utc)
        if n_coords != n_times:
            raise ValueError(
                f"trajectory has {n_coords} coordinates but "
                f"trajectory_timestamps_utc has {n_times} entries; "
                f"they must have a strict 1:1 mapping."
            )
        return self
