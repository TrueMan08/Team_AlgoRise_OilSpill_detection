from fastapi import APIRouter

from app.models.replay import Replay
from app.services.replay import get_replay

router = APIRouter()


@router.get(
    "/replay/{id}",
    summary="Get Incident Replay",
    response_model=Replay,
    responses={
        200: {"description": "Chronological replay frames (slick + vessel "
                             "states) for the incident."},
        404: {"description": "Unknown incident id."},
    },
)
async def replay(id: str) -> Replay:
    return get_replay(id)
