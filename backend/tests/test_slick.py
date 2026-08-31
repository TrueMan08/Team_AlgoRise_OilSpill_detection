from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.geometry import (
    GeoJSONMultiPolygon,
    GeoJSONPolygon,
    Point,
)
from app.models.slick import Slick

# Sample valid polygon coordinates
VALID_RING_1 = [
    [72.83, 18.92],
    [72.84, 18.92],
    [72.84, 18.93],
    [72.83, 18.93],
    [72.83, 18.92],
]

VALID_RING_2 = [
    [73.10, 19.10],
    [73.20, 19.10],
    [73.20, 19.20],
    [73.10, 19.20],
    [73.10, 19.10],
]


# ==========================================
# Point Tests
# ==========================================

def test_valid_point() -> None:
    point = Point(lat=18.9220, lon=72.8347)
    assert point.lat == 18.9220
    assert point.lon == 72.8347


def test_invalid_point_lat_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        Point(lat=95.0, lon=72.8347)

    with pytest.raises(ValidationError):
        Point(lat=-90.1, lon=72.8347)


def test_invalid_point_lon_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        Point(lat=18.9220, lon=185.0)

    with pytest.raises(ValidationError):
        Point(lat=18.9220, lon=-180.1)


# ==========================================
# GeoJSONPolygon Tests
# ==========================================

def test_valid_polygon() -> None:
    polygon = GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING_1])
    assert polygon.type == "Polygon"
    assert len(polygon.coordinates) == 1
    assert len(polygon.coordinates[0]) == 5


def test_polygon_empty_coordinates_raises_error() -> None:
    with pytest.raises(ValidationError, match="Polygon must contain at least one ring"):
        GeoJSONPolygon(type="Polygon", coordinates=[])


def test_polygon_insufficient_points_raises_error() -> None:
    with pytest.raises(ValidationError, match="must contain at least 4 coordinates"):
        GeoJSONPolygon(
            type="Polygon",
            coordinates=[
                [
                    [72.83, 18.92],
                    [72.84, 18.92],
                    [72.83, 18.92],
                ]
            ],
        )


def test_polygon_unclosed_ring_raises_error() -> None:
    with pytest.raises(ValidationError, match="A polygon ring must be closed"):
        GeoJSONPolygon(
            type="Polygon",
            coordinates=[
                [
                    [72.83, 18.92],
                    [72.84, 18.92],
                    [72.84, 18.93],
                    [72.83, 18.93],
                ]
            ],
        )


def test_polygon_invalid_coordinate_dimension_raises_error() -> None:
    with pytest.raises(ValidationError, match="Each coordinate must be"):
        GeoJSONPolygon(
            type="Polygon",
            coordinates=[
                [
                    [72.83, 18.92, 10.0],  # 3 elements
                    [72.84, 18.92],
                    [72.84, 18.93],
                    [72.83, 18.92, 10.0],
                ]
            ],
        )


def test_polygon_invalid_coordinates_range_raises_error() -> None:
    with pytest.raises(ValidationError, match="Longitude must be between"):
        GeoJSONPolygon(
            type="Polygon",
            coordinates=[
                [
                    [200.0, 18.92],
                    [72.84, 18.92],
                    [72.84, 18.93],
                    [200.0, 18.92],
                ]
            ],
        )

    with pytest.raises(ValidationError, match="Latitude must be between"):
        GeoJSONPolygon(
            type="Polygon",
            coordinates=[
                [
                    [72.83, -95.0],
                    [72.84, 18.92],
                    [72.84, 18.93],
                    [72.83, -95.0],
                ]
            ],
        )


# ==========================================
# GeoJSONMultiPolygon Tests
# ==========================================

def test_valid_multipolygon() -> None:
    multipolygon = GeoJSONMultiPolygon(
        type="MultiPolygon",
        coordinates=[[VALID_RING_1], [VALID_RING_2]],
    )
    assert multipolygon.type == "MultiPolygon"
    assert len(multipolygon.coordinates) == 2


def test_multipolygon_empty_coordinates_raises_error() -> None:
    with pytest.raises(ValidationError, match="MultiPolygon must contain at least one polygon"):
        GeoJSONMultiPolygon(type="MultiPolygon", coordinates=[])


def test_multipolygon_empty_polygon_entry_raises_error() -> None:
    with pytest.raises(
        ValidationError,
        match="Each polygon in a MultiPolygon must contain at least one ring",
    ):
        GeoJSONMultiPolygon(type="MultiPolygon", coordinates=[[]])


def test_multipolygon_unclosed_ring_raises_error() -> None:
    invalid_ring = [
        [72.83, 18.92],
        [72.84, 18.92],
        [72.84, 18.93],
        [72.83, 18.93],
    ]
    with pytest.raises(ValidationError, match="A polygon ring must be closed"):
        GeoJSONMultiPolygon(type="MultiPolygon", coordinates=[[invalid_ring]])


# ==========================================
# Slick Model Tests (Polygon & MultiPolygon)
# ==========================================

def test_valid_slick_with_polygon() -> None:
    slick_data = {
        "id": "slick-polygon-001",
        "timestamp_utc": datetime.now(timezone.utc),
        "centroid": {"lat": 18.92, "lon": 72.83},
        "geometry": {
            "type": "Polygon",
            "coordinates": [VALID_RING_1],
        },
        "area_km2": 12.45,
        "confidence": 0.94,
        "scene_id": "S1A_IW_GRDH_1SDV_20260827",
        "sensor": "Sentinel-1 SAR",
    }
    slick = Slick(**slick_data)
    assert slick.id == "slick-polygon-001"
    assert slick.area_km2 == 12.45
    assert slick.confidence == 0.94
    assert isinstance(slick.geometry, GeoJSONPolygon)
    assert slick.geometry.type == "Polygon"


def test_valid_slick_with_multipolygon() -> None:
    slick_data = {
        "id": "slick-multi-001",
        "timestamp_utc": datetime.now(timezone.utc),
        "centroid": {"lat": 19.01, "lon": 72.90},
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[VALID_RING_1], [VALID_RING_2]],
        },
        "area_km2": 25.80,
        "confidence": 0.88,
        "sensor": "Sentinel-2 MSI",
    }
    slick = Slick(**slick_data)
    assert slick.id == "slick-multi-001"
    assert slick.area_km2 == 25.80
    assert slick.confidence == 0.88
    assert isinstance(slick.geometry, GeoJSONMultiPolygon)
    assert slick.geometry.type == "MultiPolygon"
    assert slick.scene_id is None


def test_slick_invalid_geometry_discriminator() -> None:
    slick_data = {
        "id": "slick-invalid-geom",
        "timestamp_utc": datetime.now(timezone.utc),
        "centroid": {"lat": 18.92, "lon": 72.83},
        "geometry": {
            "type": "Point",  # Invalid for GeoJSONGeometry discriminator
            "coordinates": [72.83, 18.92],
        },
        "area_km2": 5.0,
        "confidence": 0.8,
    }
    with pytest.raises(ValidationError):
        Slick(**slick_data)


def test_slick_area_and_confidence_bounds() -> None:
    base_data = {
        "id": "slick-bounds",
        "timestamp_utc": datetime.now(timezone.utc),
        "centroid": {"lat": 18.92, "lon": 72.83},
        "geometry": {
            "type": "Polygon",
            "coordinates": [VALID_RING_1],
        },
    }

    # Negative area
    with pytest.raises(ValidationError):
        Slick(**base_data, area_km2=-1.0, confidence=0.5)

    # Confidence > 1.0
    with pytest.raises(ValidationError):
        Slick(**base_data, area_km2=5.0, confidence=1.05)

    # Confidence < 0.0
    with pytest.raises(ValidationError):
        Slick(**base_data, area_km2=5.0, confidence=-0.1)
