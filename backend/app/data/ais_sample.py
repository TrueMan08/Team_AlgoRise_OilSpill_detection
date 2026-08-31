"""
Synthetic AIS dataset for OilTrace MVP demo.

IMPORTANT — SYNTHETIC DATA NOTICE
===================================
This dataset is entirely synthetic and deterministic. It was purpose-built
to demonstrate the scoring mechanics of the AIS Reconstruction & Vessel
Attribution module. It does NOT represent real vessel traffic, real vessel
identities, or real oil spill incidents.

Rationale for synthetic data (SIH requirement):
- The SIH 2026 problem statement explicitly permits synthetic AIS when
  real Indian Ocean historical AIS data is unavailable.
- No freely accessible historical Indian-ocean vessel-level AIS archive
  has been identified for use in the demo.
- Synthetic data provides a controlled, reproducible evaluation scenario.

Canonical incident parameters (aligned with team test suite):
- Satellite acquisition : 2026-08-27T04:00:00Z  (Sentinel-1A)
- Slick detection       : 2026-08-27T04:05:00Z
- Slick location        : lat=18.92°N, lon=72.83°E (Arabian Sea, ~10 km W of Mumbai)
- Source polygon        : ~4 km × 2 km box centred on slick (DEMO_SOURCE_POLYGON_RING)
- Release window        : 2026-08-26T22:00Z → 2026-08-27T02:00Z

Five synthetic vessels (explained below):
  123456789  Tanker    STRONG    – passes through source area during release window  → High
  234567890  Cargo     MEDIUM    – 8 km north of source, right time, no intersection  → Medium
  345678901  Fishing   TEMPORAL  – intersects source but 12 h before release window   → High score, low temporal
  456789012  Cargo     ELIM      – 200+ km away → hard-filtered by 150 km limit
  567890123  Tanker    GAP       – passes 3 km east, has 45-min AIS gap, 2 segments
"""

from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Demo scenario constants — kept here so services and tests can import them
# ---------------------------------------------------------------------------

#: Closed GeoJSON exterior ring (lon, lat) for the demo source polygon.
DEMO_SOURCE_POLYGON_RING: list[list[float]] = [
    [72.81, 18.91],
    [72.85, 18.91],
    [72.85, 18.93],
    [72.81, 18.93],
    [72.81, 18.91],
]

#: Estimated release window from the hindcast module (demo values).
DEMO_RELEASE_WINDOW_START: datetime = datetime(2026, 8, 26, 22, 0, 0, tzinfo=timezone.utc)
DEMO_RELEASE_WINDOW_END: datetime = datetime(2026, 8, 27, 2, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# NORWAY SHOWCASE INCIDENT — the canonical full-chain demo (decided 31 Aug).
# The ONLY region where detection-style slick input, forcing data
# (data/currents.nc / wind.nc: 59-61N, 4-6E, 20-22 Aug 2025) and the AIS
# fleet all align, so the real chain
#   slick -> /hindcast -> /vessels -> /attribute -> /forward -> /replay
# runs end-to-end. The Mumbai constants above remain for the attribution
# unit tests and the Mumbai-only replay fixture.
# Scenario: tanker 678901234 crosses the slick point ~09:26Z inside the
# release window; cargo 789012345 passes ~12 km north (medium suspect);
# fisher 890123456 sailed the previous evening (temporal mismatch).
# ---------------------------------------------------------------------------

SHOWCASE_INCIDENT_ID: str = "incident-norway-001"

#: Observed slick for the showcase incident (inside the forcing window).
NORWAY_SLICK_LAT: float = 60.044
NORWAY_SLICK_LON: float = 4.482
NORWAY_OBSERVATION_TIME: datetime = datetime(2025, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

#: Closed GeoJSON exterior ring (lon, lat) around the hindcast source area
#: (live-verified: 3 h backward run puts the source centroid near 60.06N 4.43E).
NORWAY_SOURCE_POLYGON_RING: list[list[float]] = [
    [4.38, 60.02],
    [4.53, 60.02],
    [4.53, 60.10],
    [4.38, 60.10],
    [4.38, 60.02],
]

#: Release window matching the live 3 h backward hindcast from the
#: observation time.
NORWAY_RELEASE_WINDOW_START: datetime = datetime(2025, 8, 20, 9, 0, 0, tzinfo=timezone.utc)
NORWAY_RELEASE_WINDOW_END: datetime = datetime(2025, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _utc(date_str: str, time_str: str) -> datetime:
    """Parse a 'YYYY-MM-DD' + 'HH:MM' pair into a UTC-aware datetime."""
    return datetime.strptime(f"{date_str}T{time_str}", "%Y-%m-%dT%H:%M").replace(
        tzinfo=timezone.utc
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_ais_records() -> list[dict]:
    """
    Return the complete list of synthetic AIS observation records.

    Each record is a plain dict with the following keys:
        mmsi            str           – 9-digit MMSI
        name            str           – Vessel name
        vessel_type_code int          – AIS vessel type code
        vessel_type     str           – Human-readable type
        timestamp_utc   datetime(UTC) – Observation time
        lat             float         – WGS84 latitude
        lon             float         – WGS84 longitude
        sog             float         – Speed over ground (knots)
        cog             float         – Course over ground (degrees)
        heading         float         – True heading (degrees)

    The list is reproducible across calls (no random numbers).
    """
    records: list[dict] = []

    # ------------------------------------------------------------------
    # Vessel 1 — Strong Tanker  MMSI 123456789
    # Route  : south → north along 72.830°E, lat 18.70 → 19.30
    # Passes : through source polygon (~18.91–18.93°N) at ~2026-08-27T00:00Z
    # AIS    : continuous, every 15 min, 2026-08-26T18:00Z → 2026-08-27T06:00Z
    # ------------------------------------------------------------------
    _v1_origin = _utc("2026-08-26", "18:00")
    _v1_n = 49  # 49 × 15 min = 12 h
    for i in range(_v1_n):
        ts = _v1_origin + timedelta(minutes=15 * i)
        lat = round(18.70 + (i / (_v1_n - 1)) * 0.60, 5)  # 18.70 → 19.30
        records.append({
            "mmsi": "123456789",
            "name": "MV ARABIAN STAR",
            "vessel_type_code": 80,
            "vessel_type": "Tanker",
            "timestamp_utc": ts,
            "lat": lat,
            "lon": 72.830,
            "sog": 12.5,
            "cog": 0.0,
            "heading": 0.0,
        })

    # ------------------------------------------------------------------
    # Vessel 2 — Cargo (Medium)  MMSI 234567890
    # Route  : east → west at lat 18.995 (~9 km north of source centre)
    # Passes : during release window; does NOT intersect source polygon
    # AIS    : continuous, every 20 min, 2026-08-26T20:00Z → 2026-08-27T04:00Z
    # ------------------------------------------------------------------
    _v2_origin = _utc("2026-08-26", "20:00")
    _v2_n = 25  # 25 × 20 min = ~8 h 20 min
    for i in range(_v2_n):
        ts = _v2_origin + timedelta(minutes=20 * i)
        lon = round(73.20 - (i / (_v2_n - 1)) * 1.00, 5)  # 73.20 → 72.20
        records.append({
            "mmsi": "234567890",
            "name": "MV GUJARAT PRIDE",
            "vessel_type_code": 70,
            "vessel_type": "Cargo",
            "timestamp_utc": ts,
            "lat": 18.995,
            "lon": lon,
            "sog": 10.0,
            "cog": 270.0,
            "heading": 270.0,
        })

    # ------------------------------------------------------------------
    # Vessel 3 — Fishing (Temporal mismatch)  MMSI 345678901
    # Route  : south → north along 72.828°E; intersects source polygon
    # Time   : 2026-08-26T08:00Z → 16:00Z  (12 h BEFORE release window)
    # AIS    : continuous, every 20 min
    # ------------------------------------------------------------------
    _v3_origin = _utc("2026-08-26", "08:00")
    _v3_n = 25  # 25 × 20 min = ~8 h 20 min
    for i in range(_v3_n):
        ts = _v3_origin + timedelta(minutes=20 * i)
        lat = round(18.75 + (i / (_v3_n - 1)) * 0.40, 5)  # 18.75 → 19.15
        records.append({
            "mmsi": "345678901",
            "name": "FV KONKAN FISHER",
            "vessel_type_code": 30,
            "vessel_type": "Fishing",
            "timestamp_utc": ts,
            "lat": lat,
            "lon": 72.828,
            "sog": 5.0,
            "cog": 0.0,
            "heading": 0.0,
        })

    # ------------------------------------------------------------------
    # Vessel 4 — Container (Hard-filtered)  MMSI 456789012
    # Location: lat ~20.5, lon ~70.5  (≈ 220 km NW — beyond 150 km limit)
    # Time    : 2026-08-26T20:00Z → 2026-08-27T04:00Z (inside temporal window)
    # AIS     : every 30 min
    # ------------------------------------------------------------------
    _v4_origin = _utc("2026-08-26", "20:00")
    for i in range(17):  # 17 × 30 min = 8 h
        ts = _v4_origin + timedelta(minutes=30 * i)
        records.append({
            "mmsi": "456789012",
            "name": "MV MUNDRA EXPRESS",
            "vessel_type_code": 71,
            "vessel_type": "Cargo",
            "timestamp_utc": ts,
            "lat": round(20.50 + i * 0.01, 5),
            "lon": 70.50,
            "sog": 14.0,
            "cog": 90.0,
            "heading": 90.0,
        })

    # ------------------------------------------------------------------
    # Vessel 5 — Gap Tanker  MMSI 567890123
    # Route  : south → north along 72.868°E  (~4 km east of source)
    # Has a 45-min AIS gap from 2026-08-26T23:00Z → 23:45Z
    # Segment A: 2026-08-26T20:00Z → 23:00Z (13 points, every 15 min)
    # Segment B: 2026-08-26T23:45Z → 2026-08-27T03:00Z (14 points, every 15 min)
    # ------------------------------------------------------------------
    # Segment A
    _v5a_origin = _utc("2026-08-26", "20:00")
    _v5a_n = 13
    for i in range(_v5a_n):
        ts = _v5a_origin + timedelta(minutes=15 * i)
        lat = round(18.60 + (i / (_v5a_n - 1)) * 0.35, 5)  # 18.60 → 18.95
        records.append({
            "mmsi": "567890123",
            "name": "MT BOMBAY HIGH",
            "vessel_type_code": 80,
            "vessel_type": "Tanker",
            "timestamp_utc": ts,
            "lat": lat,
            "lon": 72.868,
            "sog": 11.0,
            "cog": 0.0,
            "heading": 0.0,
        })
    # --- GAP: 23:00 → 23:45  (45 minutes, no records) ---

    # Segment B
    _v5b_origin = _utc("2026-08-26", "23:45")
    _v5b_n = 14
    for i in range(_v5b_n):
        ts = _v5b_origin + timedelta(minutes=15 * i)
        lat = round(18.95 + (i / (_v5b_n - 1)) * 0.35, 5)  # 18.95 → 19.30
        records.append({
            "mmsi": "567890123",
            "name": "MT BOMBAY HIGH",
            "vessel_type_code": 80,
            "vessel_type": "Tanker",
            "timestamp_utc": ts,
            "lat": lat,
            "lon": 72.868,
            "sog": 11.0,
            "cog": 0.0,
            "heading": 0.0,
        })

    # ------------------------------------------------------------------
    # Vessel 6 — Norway Strong Tanker  MMSI 678901234
    # Route  : south → north along 4.482°E, lat 59.50 → 60.50
    # Passes : through source polygon (~60.044°N) at ~2025-08-20T09:00Z
    # AIS    : continuous, every 15 min, 2025-08-20T04:00Z → 2025-08-20T14:00Z
    # ------------------------------------------------------------------
    _v6_origin = _utc("2025-08-20", "04:00")
    _v6_n = 41  # 41 × 15 min = 10 h
    for i in range(_v6_n):
        ts = _v6_origin + timedelta(minutes=15 * i)
        lat = round(59.50 + (i / (_v6_n - 1)) * 1.00, 5)  # 59.50 → 60.50
        records.append({
            "mmsi": "678901234",
            "name": "NORWAY DEMO TANKER",
            "vessel_type_code": 80,
            "vessel_type": "Tanker",
            "timestamp_utc": ts,
            "lat": lat,
            "lon": 4.482,
            "sog": 12.5,
            "cog": 0.0,
            "heading": 0.0,
        })

    # ------------------------------------------------------------------
    # Vessel 7 — Norway Cargo (Medium)  MMSI 789012345
    # Route  : east → west at lat 60.150 (~11 km north of source centre)
    # Passes : during release window; does NOT intersect source polygon
    # AIS    : continuous, every 20 min, 2025-08-20T05:00Z → 2025-08-20T13:00Z
    # ------------------------------------------------------------------
    _v7_origin = _utc("2025-08-20", "05:00")
    _v7_n = 25  # 25 × 20 min = 8 h
    for i in range(_v7_n):
        ts = _v7_origin + timedelta(minutes=20 * i)
        lon = round(5.00 - (i / (_v7_n - 1)) * 1.00, 5)  # 5.00 → 4.00
        records.append({
            "mmsi": "789012345",
            "name": "NORWAY DEMO CARGO",
            "vessel_type_code": 70,
            "vessel_type": "Cargo",
            "timestamp_utc": ts,
            "lat": 60.150,
            "lon": lon,
            "sog": 10.0,
            "cog": 270.0,
            "heading": 270.0,
        })

    # ------------------------------------------------------------------
    # Vessel 8 — Norway Fishing (Temporal mismatch)  MMSI 890123456
    # Route  : south → north along 4.480°E; intersects source polygon
    # Time   : 2025-08-19T18:00Z → 2025-08-19T23:00Z (7h BEFORE release window)
    # AIS    : continuous, every 20 min
    # ------------------------------------------------------------------
    _v8_origin = _utc("2025-08-19", "18:00")
    _v8_n = 16  # 16 × 20 min = 5 h
    for i in range(_v8_n):
        ts = _v8_origin + timedelta(minutes=20 * i)
        lat = round(59.80 + (i / (_v8_n - 1)) * 0.40, 5)  # 59.80 → 60.20
        records.append({
            "mmsi": "890123456",
            "name": "NORWAY DEMO FISHER",
            "vessel_type_code": 30,
            "vessel_type": "Fishing",
            "timestamp_utc": ts,
            "lat": lat,
            "lon": 4.480,
            "sog": 5.0,
            "cog": 0.0,
            "heading": 0.0,
        })

    return records
