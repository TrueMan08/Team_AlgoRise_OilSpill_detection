"""Detection service: proxies the deployed OilTrace SAR+ML service
(Satyam's module) and adapts its GeoJSON FeatureCollection into the
backend's Slick contract.

ML service reference: docs/OilTrace_Detection_API.md
Live URL configured via settings.ML_SERVICE_URL.
"""
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.models.slick import Slick


def features_to_slicks(
    feature_collection: dict[str, Any],
    timestamp_utc: datetime,
) -> list[Slick]:
    """Map the ML service's FeatureCollection to Slick objects.

    Pure function so the contract mapping is unit-testable without any
    network. An empty features list is a valid result (clean water).
    """
    slicks: list[Slick] = []
    for feature in feature_collection.get("features", []):
        props = feature["properties"]
        slicks.append(
            Slick(
                id=props["id"],
                timestamp_utc=timestamp_utc,
                centroid=props["centroid"],       # {lat, lon} matches Point
                geometry=feature["geometry"],     # Polygon | MultiPolygon
                area_km2=props["area_km2"],
                confidence=props["confidence"],
                sensor="Sentinel-1 SAR",
                scene_id=props.get("scene_id"),
            )
        )
    return slicks


async def detect_oil_spill(
    image: UploadFile,
    acquired_at_utc: datetime | None = None,
) -> list[Slick]:
    """Run oil-spill detection on an uploaded scene via the ML service.

    The scene's sensing time cannot be derived from the imagery (the
    dataset's TIFFs carry no acquisition timestamp), so the caller should
    pass ``acquired_at_utc``; processing time is the documented fallback
    for the MVP/demo path.
    """
    raw = await image.read()
    async with httpx.AsyncClient(timeout=settings.ML_SERVICE_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{settings.ML_SERVICE_URL}/detect",
                # The ML service expects the multipart field name 'file'.
                files={"file": (image.filename or "scene.tif", raw, "image/tiff")},
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504,
                detail="ML service timed out (cold start can add ~40s; retry once).",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"ML service unreachable: {exc}",
            ) from exc

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text[:200])
        except ValueError:
            detail = response.text[:200]
        raise HTTPException(
            status_code=response.status_code,
            detail=f"ML service: {detail}",
        )

    timestamp = acquired_at_utc or datetime.now(timezone.utc)
    return features_to_slicks(response.json(), timestamp)


async def ml_service_health() -> dict[str, Any]:
    """Reachability probe for the ML service (used by /health/ml)."""
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.get(f"{settings.ML_SERVICE_URL}/health")
        return {
            "ml_service": "up" if response.status_code == 200 else "degraded",
            "status_code": response.status_code,
            "url": settings.ML_SERVICE_URL,
        }
    except httpx.HTTPError as exc:
        return {
            "ml_service": "down",
            "error": str(exc),
            "url": settings.ML_SERVICE_URL,
        }
