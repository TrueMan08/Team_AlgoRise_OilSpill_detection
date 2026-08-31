from datetime import datetime

from fastapi import APIRouter, File, Form, UploadFile

from app.models.slick import Slick
from app.services.detection import detect_oil_spill, ml_service_health

router = APIRouter()


@router.post(
    "/detect",
    summary="Detect Oil Spills",
    response_model=list[Slick],
    description=(
        "Runs SAR+ML oil-spill detection on an uploaded satellite scene via "
        "the OilTrace ML service. Returns ALL detected slicks, largest first "
        "(a scene routinely contains several); an empty list means no oil "
        "was detected. Live inference takes ~20-60s plus up to ~40s cold "
        "start - treat as a long call."
    ),
)
async def detect(
    image: UploadFile = File(
        ...,
        description="Georeferenced 2-band (VV,VH) Sentinel-1 GeoTIFF, Sigma0 dB, <=80 MB",
    ),
    acquired_at_utc: datetime | None = Form(
        default=None,
        description=(
            "Scene sensing time (UTC, timezone-aware). The imagery itself "
            "carries no acquisition timestamp, so supply it from scene "
            "metadata; omitted = processing time is used (demo fallback)."
        ),
    ),
) -> list[Slick]:
    return await detect_oil_spill(image, acquired_at_utc)


@router.get(
    "/health/ml",
    summary="ML Service Health",
    description="Reachability of the OilTrace detection service (also warms it up).",
)
async def health_ml() -> dict:
    return await ml_service_health()
