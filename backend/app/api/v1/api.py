from fastapi import APIRouter

from app.api.v1.endpoints import (
    attribution,
    counterfactual,
    detection,
    health,
    hindcast,
    replay,
    vessels,
)

api_router = APIRouter()

# Register endpoint routers
api_router.include_router(health.router, tags=["System & Health"])
api_router.include_router(detection.router, tags=["Detection"])
api_router.include_router(hindcast.router, tags=["Hindcast"])
api_router.include_router(vessels.router, tags=["Vessels"])
api_router.include_router(attribution.router, tags=["Attribution"])
api_router.include_router(counterfactual.router, tags=["Drift"])
api_router.include_router(replay.router, tags=["Replay"])
