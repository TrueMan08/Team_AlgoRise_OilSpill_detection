from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .source_candidate_region import SourceCandidateRegion
from .validation import UTCDateTime


class SourceRegion(BaseModel):
    id: str
    slick_id: str

    candidate_regions: list[SourceCandidateRegion] = Field(
        ...,
        min_length=1,
    )

    generated_at_utc: UTCDateTime

    @field_validator("candidate_regions")
    @classmethod
    def validate_candidate_regions(cls, regions):
        ids = [region.id for region in regions]

        if len(ids) != len(set(ids)):
            raise ValueError(
                "Candidate region IDs must be unique within a SourceRegion."
            )

        return regions
