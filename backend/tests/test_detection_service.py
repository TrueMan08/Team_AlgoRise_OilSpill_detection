"""Contract-mapping tests for the ML-service adapter (no network).

The FeatureCollection fixtures mirror the REAL response shape of the
deployed OilTrace detection service (docs/OilTrace_Detection_API.md).
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.geometry import GeoJSONMultiPolygon, GeoJSONPolygon
from app.services.detection import features_to_slicks

TS = datetime(2026, 8, 30, 9, 51, 4, tzinfo=timezone.utc)

RING = [
    [34.86, 35.62],
    [34.88, 35.62],
    [34.88, 35.65],
    [34.86, 35.65],
    [34.86, 35.62],
]


def _feature(fid: str, geometry: dict, area: float = 266.928,
             conf: float = 0.768) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "id": fid,
            "scene_id": "00067",
            "confidence": conf,
            "area_km2": area,
            "centroid": {"lat": 35.63533, "lon": 34.8704},
            "centroid_inside_scene": True,
        },
        "geometry": geometry,
    }


def test_polygon_feature_maps_to_slick() -> None:
    fc = {"type": "FeatureCollection",
          "features": [_feature("slick_000",
                                {"type": "Polygon", "coordinates": [RING]})]}
    slicks = features_to_slicks(fc, TS)
    assert len(slicks) == 1
    s = slicks[0]
    assert s.id == "slick_000"
    assert s.timestamp_utc == TS
    assert s.centroid.lat == pytest.approx(35.63533)
    assert s.centroid.lon == pytest.approx(34.8704)
    assert isinstance(s.geometry, GeoJSONPolygon)
    assert s.area_km2 == pytest.approx(266.928)
    assert s.confidence == pytest.approx(0.768)
    assert s.sensor == "Sentinel-1 SAR"
    assert s.scene_id == "00067"


def test_multipolygon_feature_maps_to_slick() -> None:
    geom = {"type": "MultiPolygon", "coordinates": [[RING], [RING]]}
    fc = {"type": "FeatureCollection",
          "features": [_feature("slick_001", geom, area=12.5, conf=0.61)]}
    slicks = features_to_slicks(fc, TS)
    assert isinstance(slicks[0].geometry, GeoJSONMultiPolygon)


def test_multiple_features_preserve_order() -> None:
    poly = {"type": "Polygon", "coordinates": [RING]}
    fc = {"type": "FeatureCollection",
          "features": [_feature("slick_000", poly, area=266.9),
                       _feature("slick_001", poly, area=1.2, conf=0.62)]}
    slicks = features_to_slicks(fc, TS)
    assert [s.id for s in slicks] == ["slick_000", "slick_001"]
    assert slicks[0].area_km2 > slicks[1].area_km2


def test_empty_features_is_clean_water_not_error() -> None:
    fc = {"type": "FeatureCollection", "features": []}
    assert features_to_slicks(fc, TS) == []


def test_naive_timestamp_rejected_by_contract() -> None:
    fc = {"type": "FeatureCollection",
          "features": [_feature("slick_000",
                                {"type": "Polygon", "coordinates": [RING]})]}
    with pytest.raises(ValidationError):
        features_to_slicks(fc, datetime(2026, 8, 30, 9, 51, 4))  # no tzinfo
