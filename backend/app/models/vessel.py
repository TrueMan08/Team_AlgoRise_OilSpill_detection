from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .geometry import GeoJSONLineString, Point
from .validation import UTCDateTime


# ---------------------------------------------------------------------------
# Vessel Track Point
# ---------------------------------------------------------------------------

class VesselTrackPoint(BaseModel):
    """
    A single normalized AIS position report for a vessel.
    """

    timestamp_utc: UTCDateTime
    position: Point

    # Speed Over Ground, in knots.
    sog: float | None = Field(default=None, ge=0)

    # Course Over Ground, in degrees [0, 360).
    cog: float | None = Field(default=None, ge=0, lt=360)

    # True heading, in degrees [0, 360).
    heading: float | None = Field(default=None, ge=0, lt=360)

    # AIS navigational status code.
    navigation_status: int | None = Field(default=None, ge=0, le=15)


# ---------------------------------------------------------------------------
# AIS Gap
# ---------------------------------------------------------------------------

class AISGap(BaseModel):
    """
    An inferred interval during which usable AIS observations were unavailable.

    A gap is derived from consecutive AIS observations and does NOT imply
    intentional AIS shutdown or suspicious behaviour.
    """

    start_time_utc: UTCDateTime
    end_time_utc: UTCDateTime
    duration_seconds: float = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_gap(self):
        if self.end_time_utc < self.start_time_utc:
            raise ValueError(
                "end_time_utc must be greater than or equal to start_time_utc."
            )

        expected_duration = (
            self.end_time_utc - self.start_time_utc
        ).total_seconds()

        if abs(self.duration_seconds - expected_duration) > 1:
            raise ValueError(
                "duration_seconds must match the difference between "
                "start_time_utc and end_time_utc."
            )

        return self


# ---------------------------------------------------------------------------
# Vessel
# ---------------------------------------------------------------------------

class Vessel(BaseModel):
    """
    A vessel identity together with its observed AIS movement history.
    """

    # Identity
    mmsi: str
    name: str | None = None

    # AIS vessel type
    vessel_type_code: int | None = None
    vessel_type: str | None = None

    # IMO number, when available.
    imo_number: str | None = None

    # Authoritative normalized AIS observations.
    track_points: list[VesselTrackPoint] = Field(..., min_length=2)

    # Derived geometry used for map rendering and spatial operations.
    track_geometry: GeoJSONLineString

    # Inferred AIS data gaps.
    ais_gaps: list[AISGap] = Field(
        default_factory=list,
    )

    @field_validator("mmsi")
    @classmethod
    def validate_mmsi(cls, mmsi: str):
        if not mmsi.isdigit():
            raise ValueError("MMSI must contain digits only.")

        if len(mmsi) != 9:
            raise ValueError("MMSI must contain exactly 9 digits.")

        return mmsi

    @model_validator(mode="after")
    def validate_track(self):
        # Track points must be chronologically ordered.
        timestamps = [
            point.timestamp_utc
            for point in self.track_points
        ]

        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError(
                "track_points must be ordered by timestamp_utc with no duplicate timestamps."
            )

        # A LineString requires at least two positions.
        if len(self.track_geometry.coordinates) < 2:
            raise ValueError(
                "track_geometry must contain at least 2 coordinates."
            )

        return self
