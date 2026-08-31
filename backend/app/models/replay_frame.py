from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.geometry import (
    GeoJSONGeometry,
    GeoJSONPoint,
)
from app.models.validation import UTCDateTime


class ReplaySlickState(BaseModel):
    """
    Spatial state of the oil slick at a particular replay timestamp.
    """

    geometry: GeoJSONGeometry

    geometry_source: Literal[
        "observed",
        "reconstructed",
    ]


class ReplayVesselState(BaseModel):
    """
    Spatial state of a vessel at a particular replay timestamp.
    """

    mmsi: str = Field(..., min_length=9, max_length=9)

    position: GeoJSONPoint

    position_source: Literal[
        "observed",
        "interpolated",
        "inferred",
    ]

    @field_validator("mmsi")
    @classmethod
    def validate_mmsi(cls, mmsi: str) -> str:
        if not mmsi.isdigit():
            raise ValueError("MMSI must contain digits only.")
        if len(mmsi) != 9:
            raise ValueError("MMSI must contain exactly 9 digits.")
        return mmsi


class ReplayFrame(BaseModel):
    """
    Spatial snapshot of an oil-spill incident at a specific
    point in time.
    """

    timestamp_utc: UTCDateTime

    slick: ReplaySlickState | None = None

    vessels: list[ReplayVesselState] = Field(default_factory=list)

    @field_validator("vessels")
    @classmethod
    def validate_unique_vessels(cls, vessels):
        mmsis = [vessel.mmsi for vessel in vessels]
        if len(mmsis) != len(set(mmsis)):
            raise ValueError("A replay frame cannot contain duplicate vessel MMSIs.")
        return vessels
