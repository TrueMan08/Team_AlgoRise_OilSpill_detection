"""Synthetic demo data for AIS vessel attribution."""

from app.data.ais_sample import (
    DEMO_RELEASE_WINDOW_END,
    DEMO_RELEASE_WINDOW_START,
    DEMO_SOURCE_POLYGON_RING,
    load_ais_records,
)

__all__ = [
    "load_ais_records",
    "DEMO_SOURCE_POLYGON_RING",
    "DEMO_RELEASE_WINDOW_START",
    "DEMO_RELEASE_WINDOW_END",
]
