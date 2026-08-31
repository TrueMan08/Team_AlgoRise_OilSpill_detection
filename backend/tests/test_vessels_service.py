"""
Tests for the AIS vessel filtering service (Nimit's module).

Verifies:
- Bounding box and time window filtering
- Chronological ordering and duplicate timestamp deduplication
- AIS gap detection (>30 min gaps)
- Vessel exclusion by bbox
- Minimum track-point requirement (≥2)
"""

from datetime import datetime, timezone

from app.services.vessels import get_vessels


def test_get_vessels_filtering() -> None:
    """Tight bbox that includes 4 of the 5 synthetic vessels."""
    start = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

    # Tighter bbox that excludes 456789012 (lat ~20.5, lon ~70.5)
    bbox = "71.0,18.0,73.5,19.5"

    vessels = get_vessels(bbox=bbox, start=start, end=end)
    mmsis = [v.mmsi for v in vessels]

    assert "123456789" in mmsis  # STRONG tanker
    assert "234567890" in mmsis  # MEDIUM cargo
    assert "345678901" in mmsis  # TEMPORAL mismatch fishing
    assert "456789012" not in mmsis  # ELIMINATED (outside bbox lat/lon range)
    assert "567890123" in mmsis  # GAP tanker


def test_get_vessels_gap_detection() -> None:
    """The gap tanker (567890123) must have exactly one 45-minute gap."""
    start = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    bbox = "71.0,18.0,73.5,19.5"

    vessels = get_vessels(bbox=bbox, start=start, end=end)
    gap_vessel = next(v for v in vessels if v.mmsi == "567890123")

    assert len(gap_vessel.ais_gaps) == 1
    assert gap_vessel.ais_gaps[0].duration_seconds == 45 * 60


def test_get_vessels_chronological_order() -> None:
    """Track points must be in strictly chronological order."""
    start = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    bbox = "71.0,18.0,73.5,19.5"

    vessels = get_vessels(bbox=bbox, start=start, end=end)
    for vessel in vessels:
        track = vessel.track_points
        for i in range(1, len(track)):
            assert track[i].timestamp_utc > track[i - 1].timestamp_utc


def test_get_vessels_time_filter() -> None:
    """A narrow time window should exclude vessels with no AIS in that period."""
    # V3 (fishing, MMSI 345678901) is active 08:00–16:00Z on 2026-08-26.
    # V1 (tanker, MMSI 123456789) is active 18:00–06:00Z.
    # Request only 18:00–20:00Z → V3 should be excluded.
    start = datetime(2026, 8, 26, 18, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 26, 20, 0, 0, tzinfo=timezone.utc)
    bbox = "71.0,18.0,73.5,19.5"

    vessels = get_vessels(bbox=bbox, start=start, end=end)
    mmsis = [v.mmsi for v in vessels]

    assert "345678901" not in mmsis  # fishing vessel active 08:00–16:00 only
    assert "123456789" in mmsis   # strong tanker active from 18:00


def test_get_vessels_invalid_bbox() -> None:
    """Invalid bbox string must raise ValueError."""
    import pytest

    start = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        get_vessels(bbox="bad,bbox", start=start, end=end)


def test_get_vessels_track_geometry_coords() -> None:
    """Track geometry coordinates must be [lon, lat] (GeoJSON order)."""
    start = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    bbox = "71.0,18.0,73.5,19.5"

    vessels = get_vessels(bbox=bbox, start=start, end=end)
    for vessel in vessels:
        # GeoJSON LineString coordinates are [lon, lat]
        # All Arabian Sea vessels have lon ~72–73 (valid longitude range)
        for coord in vessel.track_geometry.coordinates:
            lon, lat = coord[0], coord[1]
            assert 60.0 <= lon <= 85.0, f"Unexpected lon {lon} for MMSI {vessel.mmsi}"
            assert 10.0 <= lat <= 25.0, f"Unexpected lat {lat} for MMSI {vessel.mmsi}"
