"""API Version 1 individual endpoint routers."""

from app.api.v1.endpoints import (
    attribution,
    counterfactual,
    detection,
    health,
    hindcast,
    replay,
    vessels,
)

__all__ = [
    "attribution",
    "counterfactual",
    "detection",
    "health",
    "hindcast",
    "replay",
    "vessels",
]
