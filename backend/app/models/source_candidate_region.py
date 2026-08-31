from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.geometry import GeoJSONGeometry, Point
from app.models.validation import UTCDateTime


class SourceCandidateRegion(BaseModel):
    id: str

    geometry: GeoJSONGeometry

    centroid: Point

    start_time_utc: UTCDateTime
    end_time_utc: UTCDateTime

    probability: float = Field(..., ge=0, le=1)

    @model_validator(mode="after")
    def validate_time_window(self):
        if self.end_time_utc < self.start_time_utc:
            raise ValueError(
                "end_time_utc must be greater than or equal to start_time_utc."
            )

        return self
