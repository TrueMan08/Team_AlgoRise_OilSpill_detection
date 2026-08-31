from fastapi import APIRouter, HTTPException

from app.schemas.hindcast import (
    ForwardSimulationRequest,
    ForwardSimulationResult,
    HindcastRequest,
    HindcastResponse,
)
from app.services.hindcast import run_forward, run_hindcast

router = APIRouter()


@router.post(
    "/hindcast",
    summary="Run Backward Hindcast",
    response_model=HindcastResponse,
    description=(
        "Runs a backward OpenOil particle simulation from the detected "
        "slick observation point to reconstruct probable source regions.  "
        "Returns a SourceRegion with candidate regions (geometry, centroid, "
        "release-time window, density mass fraction) and a backward "
        "trajectory summary with 1:1 timestamp alignment."
    ),
)
async def hindcast(request: HindcastRequest) -> HindcastResponse:
    try:
        return run_hindcast(
            slick=request.slick,
            duration_hours=request.duration_hours,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Forcing data unavailable: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Hindcast failed: {exc}",
        ) from exc


@router.post(
    "/forward",
    summary="Run Forward Counterfactual Simulation",
    response_model=ForwardSimulationResult,
    description=(
        "Runs a forward OpenOil simulation from a candidate vessel's "
        "estimated release location/time to check physical plausibility "
        "against the observed slick.  Input comes from Nimit's "
        "attribution output."
    ),
)
async def forward(request: ForwardSimulationRequest) -> ForwardSimulationResult:
    try:
        return run_forward(request)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Forcing data unavailable: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Forward simulation failed: {exc}",
        ) from exc
