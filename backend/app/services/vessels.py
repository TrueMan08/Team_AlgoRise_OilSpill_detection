"""
AIS vessel filtering service — Nimit's module.

Responsibilities:
  1. Load synthetic AIS records from the demo fixture.
  2. Filter records by bounding box and time window.
  3. Group by MMSI, sort chronologically, remove duplicate timestamps.
  4. Detect AIS gaps (consecutive observations > 30 min apart).
  5. Return a list of validated Vessel domain objects.

Out of scope for this service:
  - Scoring or attribution logic  → app/services/attribution.py
  - Drift or hindcast physics     → app/services/hindcast.py (Ved)
  - SAR image processing          → app/services/detection.py (Satyam)
"""

from datetime import datetime, timezone

from app.data.ais_sample import load_ais_records
from app.models.geometry import GeoJSONLineString, Point
from app.models.vessel import AISGap, Vessel, VesselTrackPoint

# AIS gap threshold: consecutive observations separated by more than this
# duration are flagged as a data gap.
_GAP_THRESHOLD_SECONDS: float = 30.0 * 60.0  # 30 minutes


def get_vessels(
    bbox: str,
    start: datetime,
    end: datetime,
) -> list[Vessel]:
    """
    Retrieve and filter AIS vessel data for the specified area and time window.

    Args:
        bbox:  Bounding box string in the format "min_lon,min_lat,max_lon,max_lat"
               (WGS84 decimal degrees).  Example: "72.71,18.81,72.93,19.03".
        start: Window start timestamp (UTC, timezone-aware).  Inclusive.
        end:   Window end timestamp   (UTC, timezone-aware).  Inclusive.

    Returns:
        List of Vessel objects whose AIS track falls (at least partially) within
        the bounding box and time window.  Each Vessel has:
          - track_points sorted chronologically with no duplicate timestamps
          - track_geometry as a GeoJSON LineString  [lon, lat]
          - ais_gaps listing inferred observation gaps exceeding 30 minutes

        Vessels with fewer than 2 track points after filtering are silently
        excluded (Vessel model requires min_length=2).

    Notes:
        - The current implementation uses the synthetic demo dataset from
          app/data/ais_sample.py.  Replace load_ais_records() with a real
          AIS source (live API, PostGIS query, etc.) for production use.
        - AIS gaps are reported as missing evidence only; they do NOT imply
          intentional AIS shutdown or suspicious behaviour.
    """
    # --- 1. Parse bounding box ---
    try:
        parts = [float(x.strip()) for x in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must contain exactly four comma-separated values.")
        min_lon, min_lat, max_lon, max_lat = parts
    except ValueError as exc:
        raise ValueError(
            f"Invalid bbox '{bbox}'. Expected 'min_lon,min_lat,max_lon,max_lat'. {exc}"
        ) from exc

    # Normalise start/end to UTC if they carry another timezone offset.
    if start.tzinfo is not None:
        start = start.astimezone(timezone.utc)
    if end.tzinfo is not None:
        end = end.astimezone(timezone.utc)

    # --- 2. Load and filter records ---
    all_records = load_ais_records()

    filtered = [
        r for r in all_records
        if (
            min_lat <= r["lat"] <= max_lat
            and min_lon <= r["lon"] <= max_lon
            and start <= r["timestamp_utc"] <= end
        )
    ]

    # --- 3. Group by MMSI ---
    by_mmsi: dict[str, list[dict]] = {}
    for record in filtered:
        by_mmsi.setdefault(record["mmsi"], []).append(record)

    # --- 4. Build Vessel objects ---
    vessels: list[Vessel] = []

    for mmsi in sorted(by_mmsi.keys()):  # deterministic order
        raw = by_mmsi[mmsi]

        # Sort chronologically; drop duplicate timestamps (keep first).
        seen_timestamps: set[datetime] = set()
        sorted_records: list[dict] = []
        for r in sorted(raw, key=lambda x: x["timestamp_utc"]):
            ts = r["timestamp_utc"]
            if ts not in seen_timestamps:
                seen_timestamps.add(ts)
                sorted_records.append(r)

        # Vessel model requires at least 2 track points.
        if len(sorted_records) < 2:
            continue

        # Build VesselTrackPoint list.
        track_points: list[VesselTrackPoint] = [
            VesselTrackPoint(
                timestamp_utc=r["timestamp_utc"],
                position=Point(lat=r["lat"], lon=r["lon"]),
                sog=r.get("sog"),
                cog=r.get("cog"),
                heading=r.get("heading"),
            )
            for r in sorted_records
        ]

        # Detect AIS gaps (> 30-minute gaps between consecutive observations).
        ais_gaps: list[AISGap] = []
        for i in range(len(sorted_records) - 1):
            t_a = sorted_records[i]["timestamp_utc"]
            t_b = sorted_records[i + 1]["timestamp_utc"]
            gap_secs = (t_b - t_a).total_seconds()
            if gap_secs > _GAP_THRESHOLD_SECONDS:
                ais_gaps.append(
                    AISGap(
                        start_time_utc=t_a,
                        end_time_utc=t_b,
                        duration_seconds=gap_secs,
                    )
                )

        # Build GeoJSON LineString — GeoJSON coordinate order is [lon, lat].
        coords = [[r["lon"], r["lat"]] for r in sorted_records]
        track_geometry = GeoJSONLineString(type="LineString", coordinates=coords)

        # Use the first record for vessel-level metadata.
        meta = sorted_records[0]

        vessels.append(
            Vessel(
                mmsi=mmsi,
                name=meta.get("name"),
                vessel_type_code=meta.get("vessel_type_code"),
                vessel_type=meta.get("vessel_type"),
                track_points=track_points,
                track_geometry=track_geometry,
                ais_gaps=ais_gaps,
            )
        )

    return vessels
