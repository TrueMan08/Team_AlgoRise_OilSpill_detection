"""POST /api/v1/counterfactual — Ved's module.

Compares a forward simulation result against the observed slick to
produce counterfactual physical-plausibility evidence.

This is the final step in the pipeline:
    hindcast → vessels → attribute → forward → counterfactual
"""

from fastapi import APIRouter, HTTPException

from app.schemas.counterfactual import CounterfactualRequest, CounterfactualResult
from app.services.counterfactual import run_counterfactual

router = APIRouter()


@router.post(
    "/counterfactual",
    summary="Counterfactual Evidence Comparison",
    response_model=CounterfactualResult,
    tags=["Drift"],
    description=(
        "Compares the forward simulation output (predicted trajectory "
        "and footprint) against the originally observed slick to "
        "produce geometric plausibility evidence.  Metrics include "
        "the Jaccard index (spatial agreement), trajectory intersection, "
        "and centroid distance.  These are geometric overlap indicators, "
        "NOT posterior probabilities of responsibility."
    ),
)
async def counterfactual(request: CounterfactualRequest) -> CounterfactualResult:
    try:
        return run_counterfactual(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Counterfactual comparison failed: {exc}",
        ) from exc
