"""
GET /api/v1/vessels endpoint — Nimit's module.

Returns candidate vessel AIS tracks filtered by bounding box and time window.
This endpoint is called by the frontend (or by the attribution orchestrator)
after the hindcast module produces a source-region estimate.
"""

from datetime import datetime

from fastapi import APIRouter, Query

from app.models.vessel import Vessel
from app.services.vessels import get_vessels

router = APIRouter()


@router.get(
    "/vessels",
    summary="Get Candidate Vessels",
    response_model=list[Vessel],
    response_model_exclude_none=False,
    tags=["Vessels"],
    responses={
        200: {
            "description": (
                "List of vessels whose AIS track falls within the requested "
                "bounding box and time window.  May be empty when no AIS data "
                "matches the filters."
            )
        },
        422: {"description": "Validation error — invalid bbox format or timestamps."},
    },
)
async def vessels(
    bbox: str = Query(
        ...,
        description=(
            "Bounding box in the format 'min_lon,min_lat,max_lon,max_lat' "
            "(WGS84 decimal degrees).  "
            "Derive this from the source-region geometry returned by POST /hindcast, "
            "expanded by the spatial uncertainty radius."
        ),
        examples=["72.71,18.81,72.93,19.03"],
    ),
    start: datetime = Query(
        ...,
        description=(
            "Window start timestamp (ISO-8601, UTC recommended).  "
            "Should cover the release-time window from the hindcast module, "
            "expanded by ±12 h for high-recall candidate retrieval."
        ),
        examples=["2026-08-26T10:00:00Z"],
    ),
    end: datetime = Query(
        ...,
        description=(
            "Window end timestamp (ISO-8601, UTC recommended).  "
            "Must be greater than or equal to start."
        ),
        examples=["2026-08-27T14:00:00Z"],
    ),
) -> list[Vessel]:
    """
    Retrieve AIS vessel tracks within the specified bounding box and time window.

    **Typical caller flow:**

    1. Run `POST /hindcast` to get a source region + release-time window.
    2. Expand the source-region bounding box by the spatial uncertainty radius.
    3. Expand the release-time window by ±12 h.
    4. Call `GET /vessels` with the expanded bbox and time range.
    5. Pass the result to `POST /attribute`.

    **Notes:**

    - The current implementation uses the synthetic demo AIS dataset.
      Replace the data source in `app/data/ais_sample.py` for production use.
    - AIS gaps are included in the response as `ais_gaps` fields; they represent
      missing evidence only and do NOT imply intentional AIS shutdown.
    - Returned vessels are sorted by MMSI for deterministic ordering.
    """
    return get_vessels(bbox=bbox, start=start, end=end)
