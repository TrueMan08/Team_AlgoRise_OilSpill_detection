from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from app.models.geometry import GeoJSONLineString, Point
from app.models.vessel import AISGap, Vessel, VesselTrackPoint


# ==========================================
# VesselTrackPoint Tests
# ==========================================

def test_valid_vessel_track_point() -> None:
    now = datetime.now(timezone.utc)
    point = VesselTrackPoint(
        timestamp_utc=now,
        position=Point(lat=18.92, lon=72.83),
        sog=14.5,
        cog=180.0,
        heading=179.0,
        navigation_status=0,
    )
    assert point.sog == 14.5
    assert point.cog == 180.0
    assert point.heading == 179.0
    assert point.navigation_status == 0


def test_vessel_track_point_bounds() -> None:
    now = datetime.now(timezone.utc)
    pos = Point(lat=18.92, lon=72.83)

    # Negative SOG
    with pytest.raises(ValidationError):
        VesselTrackPoint(timestamp_utc=now, position=pos, sog=-1.0)

    # COG >= 360
    with pytest.raises(ValidationError):
        VesselTrackPoint(timestamp_utc=now, position=pos, cog=360.0)

    # Heading >= 360
    with pytest.raises(ValidationError):
        VesselTrackPoint(timestamp_utc=now, position=pos, heading=360.0)

    # Navigation status > 15
    with pytest.raises(ValidationError):
        VesselTrackPoint(timestamp_utc=now, position=pos, navigation_status=16)


# ==========================================
# AISGap Tests
# ==========================================

def test_valid_ais_gap() -> None:
    start = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    gap = AISGap(
        start_time_utc=start,
        end_time_utc=end,
        duration_seconds=7200.0,
    )
    assert gap.duration_seconds == 7200.0


def test_ais_gap_end_before_start_raises_error() -> None:
    start = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(
        ValidationError,
        match="end_time_utc must be greater than or equal to start_time_utc",
    ):
        AISGap(
            start_time_utc=start,
            end_time_utc=end,
            duration_seconds=7200.0,
        )


def test_ais_gap_duration_mismatch_raises_error() -> None:
    start = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(
        ValidationError,
        match="duration_seconds must match the difference between",
    ):
        AISGap(
            start_time_utc=start,
            end_time_utc=end,
            duration_seconds=3600.0,  # Expected 7200
        )


# ==========================================
# GeoJSONLineString Tests
# ==========================================

def test_valid_geojson_linestring() -> None:
    line = GeoJSONLineString(
        type="LineString",
        coordinates=[[72.83, 18.92], [72.85, 18.95]],
    )
    assert line.type == "LineString"
    assert len(line.coordinates) == 2


def test_geojson_linestring_insufficient_points() -> None:
    with pytest.raises(ValidationError, match="must contain at least 2 coordinates"):
        GeoJSONLineString(
            type="LineString",
            coordinates=[[72.83, 18.92]],
        )


def test_geojson_linestring_invalid_coordinate_dimension() -> None:
    with pytest.raises(ValidationError, match="Each GeoJSON coordinate must be"):
        GeoJSONLineString(
            type="LineString",
            coordinates=[[72.83, 18.92, 10.0], [72.85, 18.95]],
        )


def test_geojson_linestring_out_of_bounds() -> None:
    with pytest.raises(ValidationError, match="Longitude must be between"):
        GeoJSONLineString(
            type="LineString",
            coordinates=[[190.0, 18.92], [72.85, 18.95]],
        )

    with pytest.raises(ValidationError, match="Latitude must be between"):
        GeoJSONLineString(
            type="LineString",
            coordinates=[[72.83, -95.0], [72.85, 18.95]],
        )


# ==========================================
# Vessel Model Tests
# ==========================================

def test_valid_vessel() -> None:
    t0 = datetime(2026, 8, 27, 8, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    t2 = t0 + timedelta(hours=2)

    vessel = Vessel(
        mmsi="123456789",
        name="PACIFIC TRADER",
        vessel_type_code=70,
        vessel_type="Cargo",
        imo_number="IMO9876543",
        track_points=[
            VesselTrackPoint(timestamp_utc=t0, position=Point(lat=18.92, lon=72.83), sog=12.0),
            VesselTrackPoint(timestamp_utc=t1, position=Point(lat=18.95, lon=72.85), sog=11.5),
            VesselTrackPoint(timestamp_utc=t2, position=Point(lat=18.98, lon=72.88), sog=12.2),
        ],
        track_geometry=GeoJSONLineString(
            type="LineString",
            coordinates=[[72.83, 18.92], [72.85, 18.95], [72.88, 18.98]],
        ),
        ais_gaps=[
            AISGap(start_time_utc=t0, end_time_utc=t1, duration_seconds=3600.0),
        ],
    )
    assert vessel.mmsi == "123456789"
    assert vessel.name == "PACIFIC TRADER"
    assert len(vessel.track_points) == 3
    assert len(vessel.ais_gaps) == 1


def test_vessel_invalid_mmsi_length_or_characters() -> None:
    t0 = datetime(2026, 8, 27, 8, 0, 0, tzinfo=timezone.utc)
    base_data = {
        "track_points": [
            VesselTrackPoint(timestamp_utc=t0, position=Point(lat=18.92, lon=72.83)),
        ],
        "track_geometry": GeoJSONLineString(
            type="LineString",
            coordinates=[[72.83, 18.92], [72.85, 18.95]],
        ),
    }

    # Too short
    with pytest.raises(ValidationError, match="exactly 9 digits"):
        Vessel(mmsi="12345", **base_data)

    # Non-digit
    with pytest.raises(ValidationError, match="digits only"):
        Vessel(mmsi="12345678A", **base_data)


def test_vessel_unsorted_track_points_raises_error() -> None:
    t0 = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)

    with pytest.raises(
        ValidationError,
        match="track_points must be ordered by timestamp_utc",
    ):
        Vessel(
            mmsi="123456789",
            track_points=[
                VesselTrackPoint(timestamp_utc=t1, position=Point(lat=18.95, lon=72.85)),
                VesselTrackPoint(timestamp_utc=t0, position=Point(lat=18.92, lon=72.83)),  # Out of order
            ],
            track_geometry=GeoJSONLineString(
                type="LineString",
                coordinates=[[72.83, 18.92], [72.85, 18.95]],
            ),
        )


def test_vessel_empty_track_points_raises_error() -> None:
    with pytest.raises(ValidationError):
        Vessel(
            mmsi="123456789",
            track_points=[],  # min_length=1
            track_geometry=GeoJSONLineString(
                type="LineString",
                coordinates=[[72.83, 18.92], [72.85, 18.95]],
            ),
        )
