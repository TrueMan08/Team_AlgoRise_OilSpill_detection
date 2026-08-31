from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.geometry import GeoJSONPolygon
from app.models.validation import UTCDateTime


class SatelliteScene(BaseModel):
    """
    Metadata for a satellite scene used in oil spill detection.

    Captures acquisition parameters, sensor characteristics,
    and the spatial footprint of the scene.
    """

    scene_id: str

    # Sensor identity
    satellite: str
    sensor: str

    sensor_type: Literal[
        "SAR",
        "optical",
        "multispectral",
    ]

    # Acquisition parameters
    acquired_at_utc: UTCDateTime

    # Spatial resolution in meters per pixel.
    resolution_m: float = Field(..., gt=0)

    # Scene spatial footprint.
    footprint: GeoJSONPolygon

    # Processing level applied to the raw data.
    processing_level: str | None = None

    # Polarisation mode for SAR imagery (e.g. "VV", "VH", "VV+VH").
    polarisation: str | None = None

    # Incidence angle in degrees, relevant for SAR interpretation.
    incidence_angle_deg: float | None = Field(
        default=None,
        ge=0,
        le=90,
    )

    # External URL or storage path to the scene data.
    source_url: str | None = None

    @field_validator("scene_id", "satellite", "sensor")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be empty or whitespace-only.")
        return v
