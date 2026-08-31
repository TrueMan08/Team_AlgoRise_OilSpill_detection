from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from app.models.geometry import GeoJSONPoint, GeoJSONPolygon
from app.models.replay import Replay
from app.models.replay_frame import (
    ReplayFrame,
    ReplaySlickState,
    ReplayVesselState,
)

VALID_RING = [
    [72.83, 18.92],
    [72.84, 18.92],
    [72.84, 18.93],
    [72.83, 18.93],
    [72.83, 18.92],
]


# ==========================================
# GeoJSONPoint Tests
# ==========================================

def test_valid_geojson_point() -> None:
    point = GeoJSONPoint(type="Point", coordinates=[72.8347, 18.9220])
    assert point.type == "Point"
    assert point.coordinates == [72.8347, 18.9220]


def test_geojson_point_invalid_coordinate_dimension() -> None:
    with pytest.raises(ValidationError, match="Each GeoJSON coordinate must be"):
        GeoJSONPoint(type="Point", coordinates=[72.83, 18.92, 10.0])

    with pytest.raises(ValidationError, match="Each GeoJSON coordinate must be"):
        GeoJSONPoint(type="Point", coordinates=[72.83])


def test_geojson_point_out_of_bounds() -> None:
    with pytest.raises(ValidationError, match="Longitude must be between"):
        GeoJSONPoint(type="Point", coordinates=[185.0, 18.92])

    with pytest.raises(ValidationError, match="Latitude must be between"):
        GeoJSONPoint(type="Point", coordinates=[72.83, -95.0])


# ==========================================
# ReplaySlickState & ReplayVesselState Tests
# ==========================================

def test_valid_replay_slick_state() -> None:
    slick_state = ReplaySlickState(
        geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
        geometry_source="observed",
    )
    assert slick_state.geometry_source == "observed"
    assert slick_state.geometry.type == "Polygon"


def test_replay_slick_state_invalid_source() -> None:
    with pytest.raises(ValidationError):
        ReplaySlickState(
            geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
            geometry_source="estimated",  # Invalid Literal
        )


def test_valid_replay_vessel_state() -> None:
    vessel_state = ReplayVesselState(
        mmsi="123456789",
        position=GeoJSONPoint(type="Point", coordinates=[72.83, 18.92]),
        position_source="interpolated",
    )
    assert vessel_state.mmsi == "123456789"
    assert vessel_state.position_source == "interpolated"


def test_replay_vessel_state_invalid_mmsi() -> None:
    pos = GeoJSONPoint(type="Point", coordinates=[72.83, 18.92])

    with pytest.raises(ValidationError, match="digits only"):
        ReplayVesselState(mmsi="12345678A", position=pos, position_source="observed")

    with pytest.raises(ValidationError):
        ReplayVesselState(mmsi="12345", position=pos, position_source="observed")


def test_replay_vessel_state_invalid_source() -> None:
    pos = GeoJSONPoint(type="Point", coordinates=[72.83, 18.92])
    with pytest.raises(ValidationError):
        ReplayVesselState(mmsi="123456789", position=pos, position_source="manual")


# ==========================================
# ReplayFrame & Replay Tests
# ==========================================

def test_valid_replay_frame() -> None:
    now = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    frame = ReplayFrame(
        timestamp_utc=now,
        slick=ReplaySlickState(
            geometry=GeoJSONPolygon(type="Polygon", coordinates=[VALID_RING]),
            geometry_source="reconstructed",
        ),
        vessels=[
            ReplayVesselState(
                mmsi="123456789",
                position=GeoJSONPoint(type="Point", coordinates=[72.83, 18.92]),
                position_source="observed",
            )
        ],
    )
    assert frame.timestamp_utc == now
    assert frame.slick is not None
    assert len(frame.vessels) == 1


def test_valid_replay() -> None:
    t0 = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=600)
    t2 = t0 + timedelta(seconds=1200)

    replay = Replay(
        incident_id="incident-001",
        start_time_utc=t0,
        end_time_utc=t2,
        frame_interval_seconds=600,
        frames=[
            ReplayFrame(timestamp_utc=t0),
            ReplayFrame(timestamp_utc=t1),
            ReplayFrame(timestamp_utc=t2),
        ],
    )
    assert replay.incident_id == "incident-001"
    assert len(replay.frames) == 3


def test_replay_start_after_end_time_raises_error() -> None:
    t0 = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(
        ValidationError,
        match="start_time_utc must be earlier than end_time_utc",
    ):
        Replay(
            incident_id="incident-002",
            start_time_utc=t0,
            end_time_utc=t1,
            frame_interval_seconds=600,
            frames=[ReplayFrame(timestamp_utc=t1)],
        )


def test_replay_non_chronological_frames_raises_error() -> None:
    t0 = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=600)

    with pytest.raises(
        ValidationError,
        match="Replay frames must be in strictly chronological order",
    ):
        Replay(
            incident_id="incident-003",
            start_time_utc=t0,
            end_time_utc=t1,
            frame_interval_seconds=600,
            frames=[
                ReplayFrame(timestamp_utc=t1),
                ReplayFrame(timestamp_utc=t0),  # Out of order
            ],
        )


def test_replay_frame_outside_window_raises_error() -> None:
    t0 = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_early = t0 - timedelta(seconds=600)

    with pytest.raises(
        ValidationError,
        match="first replay frame must fall within",
    ):
        Replay(
            incident_id="incident-004",
            start_time_utc=t0,
            end_time_utc=t1,
            frame_interval_seconds=600,
            frames=[
                ReplayFrame(timestamp_utc=t_early),
                ReplayFrame(timestamp_utc=t0),
            ],
        )


def test_replay_interval_mismatch_raises_error() -> None:
    t0 = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=300)  # Gap is 300s, but interval declared is 600s

    with pytest.raises(
        ValidationError,
        match="Replay frame timestamps must follow frame_interval_seconds",
    ):
        Replay(
            incident_id="incident-005",
            start_time_utc=t0,
            end_time_utc=t0 + timedelta(seconds=3600),
            frame_interval_seconds=600,
            frames=[
                ReplayFrame(timestamp_utc=t0),
                ReplayFrame(timestamp_utc=t1),
            ],
        )
