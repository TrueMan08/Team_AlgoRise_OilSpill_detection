from fastapi import APIRouter, status
from app.core.config import settings
from app.schemas.health import HealthCheckResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Returns the operational status and metadata of the application.",
)
async def get_health() -> HealthCheckResponse:
    """Perform a health check on the API."""
    return HealthCheckResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )


@router.get(
    "/ping",
    status_code=status.HTTP_200_OK,
    summary="Ping Endpoint",
    description="Simple ping endpoint for quick uptime probes.",
)
async def ping() -> dict[str, str]:
    """Lightweight ping probe."""
    return {"ping": "pong"}
