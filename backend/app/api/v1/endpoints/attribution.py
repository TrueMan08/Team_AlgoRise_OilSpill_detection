"""
POST /api/v1/attribute — Nimit's module.

Accepts a hindcast source region and candidate vessel list, runs the
four-component evidence scoring, and returns:
  - all ranked Attribution objects
  - the TOP 2 candidates with release states and pre-built ForwardSimulationRequests
  - a no_strong_candidate flag when the highest score is below 0.40
"""

from fastapi import APIRouter, HTTPException

from app.schemas.attribution import AttributeRequest, AttributeResponse
from app.services.attribution import run_full_attribution

router = APIRouter()


@router.post(
    "/attribute",
    summary="Run Vessel Attribution",
    response_model=AttributeResponse,
    response_model_exclude_none=False,
    tags=["Attribution"],
    responses={
        200: {
            "description": (
                "Attribution results ranked by relative score. "
                "top_candidates contains the TOP 2 candidates with release states "
                "and pre-built ForwardSimulationRequests for POST /forward."
            )
        },
        422: {"description": "Validation error — invalid request body."},
        500: {"description": "Attribution engine error."},
    },
)
async def attribute(request: AttributeRequest) -> AttributeResponse:
    """
    Score candidate vessels against the hindcast source region.

    **Typical caller flow:**

    1. Run `POST /hindcast` → get `HindcastResponse.source_region`.
    2. Run `GET /vessels` with bbox/time derived from the source region.
    3. Call `POST /attribute` with `incident_id`, `source_region`, `vessels`.
    4. Read `response.top_candidates[0].forward_request` → send to `POST /forward`.

    **Score interpretation:**
    Attribution scores are RELATIVE ATTRIBUTION SCORES, NOT posterior probabilities.
    A high score means the vessel fits the available spatial/temporal evidence
    well under the project's heuristic; it does NOT mean confirmed responsibility.

    **Language discipline:**
    Candidates are referred to as "suspects" or "candidates", never "culprits".
    """
    try:
        return run_full_attribution(
            incident_id=request.incident_id,
            source_region=request.source_region,
            vessels=request.vessels,
            uncertainty_radius_km=request.uncertainty_radius_km,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
