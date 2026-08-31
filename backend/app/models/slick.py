from datetime import datetime

from pydantic import BaseModel, Field

from app.models.geometry import GeoJSONGeometry, Point
from app.models.validation import UTCDateTime


class Slick(BaseModel):
    id: str
    timestamp_utc: UTCDateTime

    centroid: Point
    geometry: GeoJSONGeometry

    area_km2: float = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)

    sensor: str | None = None
    scene_id: str | None = None
