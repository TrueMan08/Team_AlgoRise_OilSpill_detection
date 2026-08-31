"""Replay service — cached demo scenario (the frozen plan's demo bundle).

Builds a deterministic `Replay` for the demo incident from the synthetic
AIS fixture: vessels animate along their tracks (observed fixes, linear
interpolation between them), the reconstructed source geometry appears
during the release window, and the observed slick appears at observation
time. Unknown incident ids raise 404 — never a silent ``null``.

Production note: replace `_KNOWN_INCIDENTS` with persisted pipeline outputs
once an incident store exists; the frame-building logic is reusable as-is.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import HTTPException

from app.data.ais_sample import (
    DEMO_RELEASE_WINDOW_START,
    DEMO_SOURCE_POLYGON_RING,
    NORWAY_OBSERVATION_TIME,
    NORWAY_RELEASE_WINDOW_START,
    NORWAY_SOURCE_POLYGON_RING,
    SHOWCASE_INCIDENT_ID,
    load_ais_records,
)
from app.models.geometry import GeoJSONPoint, GeoJSONPolygon
from app.models.replay import Replay
from app.models.replay_frame import (
    ReplayFrame,
    ReplaySlickState,
    ReplayVesselState,
)

DEMO_INCIDENT_ID = "incident-demo-001"

#: Per-incident replay scenarios. SHOWCASE_INCIDENT_ID (Norway) is the
#: canonical full-chain demo; the Mumbai incident remains for the
#: attribution-only story. Vessels self-select by time: each fleet's fixes
#: only fall inside its own incident window.
_SCENARIOS: dict[str, dict] = {
    DEMO_INCIDENT_ID: {
        "start": datetime(2026, 8, 26, 18, 0, 0, tzinfo=timezone.utc),
        "observation": datetime(2026, 8, 27, 2, 0, 0, tzinfo=timezone.utc),
        "release_start": DEMO_RELEASE_WINDOW_START,
        "ring": DEMO_SOURCE_POLYGON_RING,
    },
    SHOWCASE_INCIDENT_ID: {
        "start": datetime(2025, 8, 19, 18, 0, 0, tzinfo=timezone.utc),
        "observation": NORWAY_OBSERVATION_TIME,
        "release_start": NORWAY_RELEASE_WINDOW_START,
        "ring": NORWAY_SOURCE_POLYGON_RING,
    },
}
_FRAME_INTERVAL_S = 1800  # 30 min


def _vessel_state_at(track: list[dict], ts: datetime) -> ReplayVesselState | None:
    """Observed fix at exactly ``ts``, else linear interpolation between the
    surrounding fixes; ``None`` outside the vessel's track span."""
    if ts < track[0]["timestamp_utc"] or ts > track[-1]["timestamp_utc"]:
        return None
    for i, rec in enumerate(track):
        if rec["timestamp_utc"] == ts:
            return ReplayVesselState(
                mmsi=rec["mmsi"],
                position=GeoJSONPoint(type="Point",
                                      coordinates=[rec["lon"], rec["lat"]]),
                position_source="observed",
            )
        if rec["timestamp_utc"] > ts:
            prev = track[i - 1]
            span = (rec["timestamp_utc"] - prev["timestamp_utc"]).total_seconds()
            f = ((ts - prev["timestamp_utc"]).total_seconds() / span) if span else 0.0
            lon = prev["lon"] + f * (rec["lon"] - prev["lon"])
            lat = prev["lat"] + f * (rec["lat"] - prev["lat"])
            return ReplayVesselState(
                mmsi=rec["mmsi"],
                position=GeoJSONPoint(type="Point", coordinates=[lon, lat]),
                position_source="interpolated",
            )
    return None


@lru_cache(maxsize=4)
def _build_replay(incident_id: str) -> Replay:
    sc = _SCENARIOS[incident_id]
    tracks: dict[str, list[dict]] = {}
    for rec in load_ais_records():
        tracks.setdefault(rec["mmsi"], []).append(rec)
    for track in tracks.values():
        track.sort(key=lambda r: r["timestamp_utc"])

    source_polygon = GeoJSONPolygon(type="Polygon",
                                    coordinates=[sc["ring"]])
    frames: list[ReplayFrame] = []
    ts = sc["start"]
    while ts <= sc["observation"]:
        vessels = [s for t in tracks.values()
                   if (s := _vessel_state_at(t, ts)) is not None]
        slick = None
        if ts >= sc["observation"]:
            slick = ReplaySlickState(geometry=source_polygon,
                                     geometry_source="observed")
        elif ts >= sc["release_start"]:
            slick = ReplaySlickState(geometry=source_polygon,
                                     geometry_source="reconstructed")
        frames.append(ReplayFrame(timestamp_utc=ts, slick=slick,
                                  vessels=vessels))
        ts += timedelta(seconds=_FRAME_INTERVAL_S)

    return Replay(
        incident_id=incident_id,
        start_time_utc=sc["start"],
        end_time_utc=sc["observation"],
        frame_interval_seconds=_FRAME_INTERVAL_S,
        frames=frames,
    )


def get_replay(id: str) -> Replay:
    """Retrieve temporal and spatial replay frames for an incident."""
    if id not in _SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail=(f"Unknown incident '{id}'. Available incidents: "
                    f"{sorted(_SCENARIOS)} (showcase: '{SHOWCASE_INCIDENT_ID}')."),
        )
    return _build_replay(id)
