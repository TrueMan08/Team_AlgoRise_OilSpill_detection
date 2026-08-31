import pytest
from pydantic import ValidationError

from app.models.attribution import (
    Attribution,
    EvidenceBreakdown,
    EvidenceScore,
    SourceRegionMatch,
)


# ==========================================
# EvidenceScore Tests
# ==========================================

def test_valid_evidence_score() -> None:
    score = EvidenceScore(
        score=80.0,
        weight=0.25,
        contribution=20.0,
        explanation="High spatial proximity to spill boundary.",
    )
    assert score.score == 80.0
    assert score.weight == 0.25
    assert score.contribution == 20.0
    assert "spatial proximity" in score.explanation


def test_evidence_score_contribution_mismatch_raises_error() -> None:
    with pytest.raises(
        ValidationError,
        match="contribution must equal score × weight",
    ):
        EvidenceScore(
            score=80.0,
            weight=0.25,
            contribution=25.0,  # Expected 20.0
            explanation="Invalid contribution test.",
        )


def test_evidence_score_bounds() -> None:
    # Score > 100
    with pytest.raises(ValidationError):
        EvidenceScore(
            score=105.0,
            weight=0.2,
            contribution=21.0,
            explanation="Score out of range",
        )

    # Score < 0
    with pytest.raises(ValidationError):
        EvidenceScore(
            score=-5.0,
            weight=0.2,
            contribution=-1.0,
            explanation="Negative score",
        )

    # Weight > 1
    with pytest.raises(ValidationError):
        EvidenceScore(
            score=50.0,
            weight=1.5,
            contribution=75.0,
            explanation="Weight out of range",
        )


# ==========================================
# SourceRegionMatch Tests
# ==========================================

def test_valid_source_region_match() -> None:
    match = SourceRegionMatch(
        source_candidate_region_id="cand-001",
        compatibility_score=0.92,
    )
    assert match.source_candidate_region_id == "cand-001"
    assert match.compatibility_score == 0.92


def test_source_region_match_compatibility_score_bounds() -> None:
    with pytest.raises(ValidationError):
        SourceRegionMatch(
            source_candidate_region_id="cand-002",
            compatibility_score=1.2,
        )

    with pytest.raises(ValidationError):
        SourceRegionMatch(
            source_candidate_region_id="cand-003",
            compatibility_score=-0.1,
        )


# ==========================================
# EvidenceBreakdown Tests
# ==========================================

def create_sample_breakdown(weight_override: float | None = None) -> EvidenceBreakdown:
    w1 = 0.3
    w2 = 0.2
    w3 = 0.2
    w4 = 0.15
    w5 = weight_override if weight_override is not None else 0.15

    return EvidenceBreakdown(
        spatial=EvidenceScore(score=80.0, weight=w1, contribution=80.0 * w1, explanation="Spatial check"),
        temporal=EvidenceScore(score=90.0, weight=w2, contribution=90.0 * w2, explanation="Temporal check"),
        trajectory=EvidenceScore(score=70.0, weight=w3, contribution=70.0 * w3, explanation="Trajectory check"),
        source_probability=EvidenceScore(score=85.0, weight=w4, contribution=85.0 * w4, explanation="Source prob check"),
        ais_anomaly=EvidenceScore(score=60.0, weight=w5, contribution=60.0 * w5, explanation="AIS anomaly check"),
    )


def test_valid_evidence_breakdown() -> None:
    breakdown = create_sample_breakdown()
    total_weight = (
        breakdown.spatial.weight
        + breakdown.temporal.weight
        + breakdown.trajectory.weight
        + breakdown.source_probability.weight
        + breakdown.ais_anomaly.weight
    )
    assert abs(total_weight - 1.0) < 1e-6


def test_evidence_breakdown_weights_sum_not_one_raises_error() -> None:
    with pytest.raises(
        ValidationError,
        match="Evidence weights must sum to 1.0",
    ):
        create_sample_breakdown(weight_override=0.30)  # Total weight = 1.15


# ==========================================
# Attribution Model Tests
# ==========================================

def test_valid_attribution() -> None:
    breakdown = create_sample_breakdown()
    calculated_score = (
        breakdown.spatial.contribution
        + breakdown.temporal.contribution
        + breakdown.trajectory.contribution
        + breakdown.source_probability.contribution
        + breakdown.ais_anomaly.contribution
    )

    attr = Attribution(
        incident_id="incident-2026-001",
        mmsi="987654321",
        overall_score=calculated_score,
        rank=1,
        evidence_breakdown=breakdown,
        matched_source_regions=[
            SourceRegionMatch(
                source_candidate_region_id="cand-001",
                compatibility_score=0.95,
            )
        ],
    )
    assert attr.incident_id == "incident-2026-001"
    assert attr.mmsi == "987654321"
    assert attr.rank == 1
    assert abs(attr.overall_score - calculated_score) < 1e-6
    assert len(attr.matched_source_regions) == 1


def test_attribution_overall_score_mismatch_raises_error() -> None:
    breakdown = create_sample_breakdown()
    with pytest.raises(
        ValidationError,
        match="overall_score must equal the sum of all evidence contributions",
    ):
        Attribution(
            incident_id="incident-2026-002",
            mmsi="987654321",
            overall_score=99.9,  # Mismatched score
            rank=1,
            evidence_breakdown=breakdown,
        )


def test_attribution_invalid_mmsi_raises_error() -> None:
    breakdown = create_sample_breakdown()
    calculated_score = (
        breakdown.spatial.contribution
        + breakdown.temporal.contribution
        + breakdown.trajectory.contribution
        + breakdown.source_probability.contribution
        + breakdown.ais_anomaly.contribution
    )

    # MMSI with non-digits
    with pytest.raises(ValidationError, match="digits only"):
        Attribution(
            incident_id="incident-2026-003",
            mmsi="98765432A",
            overall_score=calculated_score,
            rank=1,
            evidence_breakdown=breakdown,
        )

    # MMSI with incorrect length
    with pytest.raises(ValidationError, match="exactly 9 digits"):
        Attribution(
            incident_id="incident-2026-004",
            mmsi="12345",
            overall_score=calculated_score,
            rank=1,
            evidence_breakdown=breakdown,
        )


def test_attribution_rank_minimum() -> None:
    breakdown = create_sample_breakdown()
    calculated_score = (
        breakdown.spatial.contribution
        + breakdown.temporal.contribution
        + breakdown.trajectory.contribution
        + breakdown.source_probability.contribution
        + breakdown.ais_anomaly.contribution
    )

    # Rank 0 is invalid (ge=1)
    with pytest.raises(ValidationError):
        Attribution(
            incident_id="incident-2026-005",
            mmsi="987654321",
            overall_score=calculated_score,
            rank=0,
            evidence_breakdown=breakdown,
        )
