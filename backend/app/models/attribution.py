from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class EvidenceScore(BaseModel):
    """
    A normalized score representing one category of evidence
    used during vessel attribution.
    """

    # Strength of this evidence category.
    # 0 = completely incompatible, 100 = maximally compatible.
    score: float = Field(..., ge=0, le=100)

    # Relative importance of this evidence category.
    # All evidence weights within an Attribution must sum to 1.
    weight: float = Field(..., ge=0, le=1)

    # Weighted contribution to the overall attribution score.
    contribution: float = Field(..., ge=0, le=100)

    # Human-readable explanation of why this evidence
    # received its score.
    explanation: str

    @model_validator(mode="after")
    def validate_contribution(self):
        expected_contribution = self.score * self.weight

        # Allow a tiny tolerance for floating-point rounding.
        if abs(self.contribution - expected_contribution) > 1e-6:
            raise ValueError(
                "contribution must equal score × weight."
            )

        return self


class SourceRegionMatch(BaseModel):
    """
    Describes how strongly a vessel is compatible with
    a particular candidate source region.
    """

    source_candidate_region_id: str

    # 0 = completely incompatible
    # 1 = maximally compatible
    compatibility_score: float = Field(
        ...,
        ge=0,
        le=1,
    )


class EvidenceBreakdown(BaseModel):
    """
    The evidence categories currently used by the
    attribution engine.
    """

    spatial: EvidenceScore
    temporal: EvidenceScore
    trajectory: EvidenceScore
    source_probability: EvidenceScore
    ais_anomaly: EvidenceScore

    @model_validator(mode="after")
    def validate_weights(self):
        total_weight = (
            self.spatial.weight
            + self.temporal.weight
            + self.trajectory.weight
            + self.source_probability.weight
            + self.ais_anomaly.weight
        )

        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(
                "Evidence weights must sum to 1.0."
            )

        return self


class Attribution(BaseModel):
    """
    Evidence-based assessment of a vessel's compatibility
    with a particular oil-spill incident.

    This model does NOT represent proof of responsibility
    or probability of guilt.
    """

    incident_id: str
    mmsi: str

    # Overall compatibility score, normalized to [0, 100].
    overall_score: float = Field(..., ge=0, le=100)

    # Rank among vessels evaluated for this incident.
    rank: int = Field(..., ge=1)

    evidence_breakdown: EvidenceBreakdown

    # A vessel may legitimately have no sufficiently
    # compatible source regions.
    matched_source_regions: list[SourceRegionMatch] = Field(
        default_factory=list
    )

    @field_validator("matched_source_regions")
    @classmethod
    def validate_unique_source_matches(cls, matches):
        region_ids = [match.source_candidate_region_id for match in matches]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError(
                "A vessel attribution cannot match the same source region twice."
            )
        return matches

    @model_validator(mode="after")
    def validate_overall_score(self):
        evidence = self.evidence_breakdown

        calculated_score = (
            evidence.spatial.contribution
            + evidence.temporal.contribution
            + evidence.trajectory.contribution
            + evidence.source_probability.contribution
            + evidence.ais_anomaly.contribution
        )

        if abs(self.overall_score - calculated_score) > 1e-6:
            raise ValueError(
                "overall_score must equal the sum of all "
                "evidence contributions."
            )

        return self

    @model_validator(mode="after")
    def validate_mmsi(self):
        if not self.mmsi.isdigit():
            raise ValueError(
                "MMSI must contain digits only."
            )

        if len(self.mmsi) != 9:
            raise ValueError(
                "MMSI must contain exactly 9 digits."
            )

        return self
