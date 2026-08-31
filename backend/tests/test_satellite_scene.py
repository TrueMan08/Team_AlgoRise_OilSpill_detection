from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.geometry import GeoJSONPolygon
from app.models.satellite_scene import SatelliteScene

VALID_FOOTPRINT_RING = [
    [72.0, 18.0],
    [73.0, 18.0],
    [73.0, 19.0],
    [72.0, 19.0],
    [72.0, 18.0],
]


def make_scene(**overrides) -> SatelliteScene:
    """Helper to build a valid SatelliteScene with optional overrides."""
    defaults = {
        "scene_id": "S1A_IW_GRDH_1SDV_20260827T040000",
        "satellite": "Sentinel-1A",
        "sensor": "C-SAR",
        "sensor_type": "SAR",
        "acquired_at_utc": datetime(2026, 8, 27, 4, 0, 0, tzinfo=timezone.utc),
        "resolution_m": 10.0,
        "footprint": GeoJSONPolygon(
            type="Polygon", coordinates=[VALID_FOOTPRINT_RING]
        ),
        "processing_level": "GRD",
        "polarisation": "VV+VH",
        "incidence_angle_deg": 35.0,
        "source_url": "s3://sentinel-1/scenes/S1A_IW_GRDH_1SDV_20260827.tif",
    }
    defaults.update(overrides)
    return SatelliteScene(**defaults)


# ==========================================
# Valid SatelliteScene Tests
# ==========================================

def test_valid_satellite_scene() -> None:
    scene = make_scene()
    assert scene.scene_id == "S1A_IW_GRDH_1SDV_20260827T040000"
    assert scene.satellite == "Sentinel-1A"
    assert scene.sensor == "C-SAR"
    assert scene.sensor_type == "SAR"
    assert scene.resolution_m == 10.0
    assert scene.polarisation == "VV+VH"
    assert scene.incidence_angle_deg == 35.0
    assert scene.footprint.type == "Polygon"


def test_satellite_scene_optical_sensor() -> None:
    scene = make_scene(
        scene_id="S2B_MSI_20260827",
        satellite="Sentinel-2B",
        sensor="MSI",
        sensor_type="optical",
        resolution_m=10.0,
        polarisation=None,
        incidence_angle_deg=None,
    )
    assert scene.sensor_type == "optical"
    assert scene.polarisation is None


def test_satellite_scene_multispectral_sensor() -> None:
    scene = make_scene(
        sensor_type="multispectral",
        sensor="MODIS",
        satellite="Terra",
        resolution_m=250.0,
    )
    assert scene.sensor_type == "multispectral"


def test_satellite_scene_minimal_optional_fields() -> None:
    scene = SatelliteScene(
        scene_id="RADARSAT2_20260827",
        satellite="RADARSAT-2",
        sensor="C-SAR",
        sensor_type="SAR",
        acquired_at_utc=datetime(2026, 8, 27, 6, 0, 0, tzinfo=timezone.utc),
        resolution_m=8.0,
        footprint=GeoJSONPolygon(
            type="Polygon", coordinates=[VALID_FOOTPRINT_RING]
        ),
    )
    assert scene.processing_level is None
    assert scene.polarisation is None
    assert scene.incidence_angle_deg is None
    assert scene.source_url is None


# ==========================================
# Validation Error Tests
# ==========================================

def test_satellite_scene_invalid_sensor_type() -> None:
    with pytest.raises(ValidationError):
        make_scene(sensor_type="lidar")


def test_satellite_scene_empty_scene_id_raises_error() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        make_scene(scene_id="   ")


def test_satellite_scene_empty_satellite_raises_error() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        make_scene(satellite="")


def test_satellite_scene_empty_sensor_raises_error() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        make_scene(sensor="  ")


def test_satellite_scene_resolution_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_scene(resolution_m=0)

    with pytest.raises(ValidationError):
        make_scene(resolution_m=-5.0)


def test_satellite_scene_incidence_angle_bounds() -> None:
    # Valid boundary values
    scene_low = make_scene(incidence_angle_deg=0.0)
    assert scene_low.incidence_angle_deg == 0.0

    scene_high = make_scene(incidence_angle_deg=90.0)
    assert scene_high.incidence_angle_deg == 90.0

    # Out of range
    with pytest.raises(ValidationError):
        make_scene(incidence_angle_deg=-1.0)

    with pytest.raises(ValidationError):
        make_scene(incidence_angle_deg=91.0)
