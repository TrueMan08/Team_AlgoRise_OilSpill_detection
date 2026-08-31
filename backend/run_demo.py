"""
OilTrace AIS + Attribution Demo Script.

Demonstrates the complete Nimit pipeline:

  Hindcast-like SourceRegion
  → AIS filtering (GET /vessels)
  → Attribution scoring (POST /attribute)
  → Ranking
  → TOP 2 candidates
  → Release-state selection (polygon-distance rule)
  → Forward-simulation payload validation

Run from the repo root:
    python3 run_demo.py

IMPORTANT — SYNTHETIC DATA NOTICE:
  All AIS data is synthetic and purpose-built for scoring mechanics
  demonstration. It does NOT represent real vessel traffic or incidents.
"""

import json
from datetime import datetime, timezone

from app.data.ais_sample import (
    DEMO_RELEASE_WINDOW_END,
    DEMO_RELEASE_WINDOW_START,
    DEMO_SOURCE_POLYGON_RING,
    load_ais_records,
)
from app.models.geometry import GeoJSONPolygon, Point
from app.models.source_candidate_region import SourceCandidateRegion
from app.models.source_region import SourceRegion
from app.services.attribution import run_full_attribution
from app.services.vessels import get_vessels


def _sep(title: str = "") -> None:
    w = 72
    if title:
        pad = (w - len(title) - 2) // 2
        print("=" * pad + f" {title} " + "=" * (w - pad - len(title) - 2))
    else:
        print("=" * w)


def run() -> None:
    # -----------------------------------------------------------------------
    # 1. Show synthetic AIS fixture summary
    # -----------------------------------------------------------------------
    _sep("SYNTHETIC AIS FIXTURE")
    records = load_ais_records()
    by_mmsi: dict[str, dict] = {}
    for r in records:
        mmsi = r["mmsi"]
        if mmsi not in by_mmsi:
            by_mmsi[mmsi] = {"name": r["name"], "type": r["vessel_type"], "count": 0, "ts": []}
        by_mmsi[mmsi]["count"] += 1
        by_mmsi[mmsi]["ts"].append(r["timestamp_utc"])

    for mmsi, data in sorted(by_mmsi.items()):
        ts = sorted(data["ts"])
        print(
            f"  MMSI {mmsi}  {data['name']:<22}  {data['type']:<10}  "
            f"{data['count']:3d} obs  {ts[0].strftime('%H:%MZ')} → {ts[-1].strftime('%H:%MZ')}"
        )

    # -----------------------------------------------------------------------
    # 2. Build synthetic SourceRegion (mimics HindcastResponse.source_region)
    # -----------------------------------------------------------------------
    _sep("SYNTHETIC SOURCE REGION (mimics hindcast output)")
    candidate = SourceCandidateRegion(
        id="cand-demo",
        geometry=GeoJSONPolygon(
            type="Polygon",
            coordinates=[DEMO_SOURCE_POLYGON_RING],
        ),
        centroid=Point(lat=18.92, lon=72.83),
        start_time_utc=DEMO_RELEASE_WINDOW_START,
        end_time_utc=DEMO_RELEASE_WINDOW_END,
        probability=0.9,
    )
    source_region = SourceRegion(
        id="sr-demo",
        slick_id="slick-001",
        generated_at_utc=datetime(2026, 8, 26, 23, 0, 0, tzinfo=timezone.utc),
        candidate_regions=[candidate],
    )
    print(f"  Source polygon  : {DEMO_SOURCE_POLYGON_RING[0]} → {DEMO_SOURCE_POLYGON_RING[2]}")
    print(f"  Release window  : {DEMO_RELEASE_WINDOW_START.isoformat()} → {DEMO_RELEASE_WINDOW_END.isoformat()}")
    print(f"  Observation time: {DEMO_RELEASE_WINDOW_END.isoformat()} (= end of window = slick detection)")
    print(f"  Probability     : {candidate.probability} (KDE mass fraction — NOT calibrated probability)")

    # -----------------------------------------------------------------------
    # 3. AIS Vessel Retrieval
    # -----------------------------------------------------------------------
    _sep("AIS VESSEL RETRIEVAL")
    bbox = "70.0,17.0,74.0,21.0"
    start_filter = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)
    end_filter = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    print(f"  bbox : {bbox}")
    print(f"  start: {start_filter.isoformat()}")
    print(f"  end  : {end_filter.isoformat()}")
    print()

    retrieved_vessels = get_vessels(bbox=bbox, start=start_filter, end=end_filter)
    print(f"  Retrieved {len(retrieved_vessels)} vessels:")
    for v in retrieved_vessels:
        gaps_str = (
            f"  {len(v.ais_gaps)} gap(s): {[int(g.duration_seconds // 60) for g in v.ais_gaps]} min"
            if v.ais_gaps else "  no gaps"
        )
        print(f"    MMSI {v.mmsi}  {(v.name or '?'):<22}  {len(v.track_points):3d} pts  {gaps_str}")

    # -----------------------------------------------------------------------
    # 4. Full Attribution Pipeline (scoring + TOP 2)
    # -----------------------------------------------------------------------
    _sep("ATTRIBUTION SCORING")
    response = run_full_attribution(
        incident_id="incident-demo-001",
        source_region=source_region,
        vessels=retrieved_vessels,
        uncertainty_radius_km=10.0,
    )

    print(f"  Total candidates scored: {len(response.all_attributions)}")
    print(f"  no_strong_candidate    : {response.no_strong_candidate}")
    print()

    print(f"  {'Rank':<5} {'MMSI':<12} {'Name':<22} {'Score':>7}  {'Conf':<8}  {'Dist km':>8}")
    print(f"  {'-'*5} {'-'*12} {'-'*22} {'-'*7}  {'-'*8}  {'-'*8}")
    for attr in response.all_attributions:
        bd = attr.evidence_breakdown
        cand_detail = next(
            (c for c in response.top_candidates if c.vessel_mmsi == attr.mmsi),
            None,
        )
        dist_str = f"{cand_detail.min_distance_km:.2f}" if cand_detail else "—"
        vessel_name = next((v.name for v in retrieved_vessels if v.mmsi == attr.mmsi), "?") or "?"
        print(
            f"  {attr.rank:<5} {attr.mmsi:<12} {vessel_name:<22} {attr.overall_score:7.2f}  "
            f"{(cand_detail.confidence if cand_detail else '?'):<8}  {dist_str:>8}"
        )

    # -----------------------------------------------------------------------
    # 5. TOP 2 Candidates — Release States
    # -----------------------------------------------------------------------
    _sep("TOP 2 CANDIDATES — RELEASE STATES (Nimit → Ved handoff)")
    if not response.top_candidates:
        print("  No strong candidates found. Increase search area or check AIS data.")
        return

    for cand in response.top_candidates:
        print()
        print(f"  ╔══ RANK {cand.rank} ═══════════════════════════════════════════════════")
        print(f"  ║  MMSI           : {cand.vessel_mmsi}")
        print(f"  ║  Name / Type    : {cand.vessel_name} / {cand.vessel_type}")
        print(f"  ║  Overall score  : {cand.overall_score:.2f} / 100.00")
        print(f"  ║  Confidence     : {cand.confidence}")
        print(f"  ║  Min dist (km)  : {cand.min_distance_km:.4f}")
        print(f"  ║")
        print(f"  ║  Evidence breakdown:")
        print(f"  ║    Spatial      : {cand.spatial_score:.4f}  ×  0.35  =  {cand.spatial_score * 0.35 * 100:.4f}")
        print(f"  ║    Temporal     : {cand.temporal_score:.4f}  ×  0.30  =  {cand.temporal_score * 0.30 * 100:.4f}")
        print(f"  ║    Trajectory   : {cand.trajectory_score:.4f}  ×  0.20  =  {cand.trajectory_score * 0.20 * 100:.4f}")
        print(f"  ║    AIS Reliab.  : {cand.ais_reliability_score:.4f}  ×  0.15  =  {cand.ais_reliability_score * 0.15 * 100:.4f}")
        print(f"  ║")
        print(f"  ║  Release state (from real AIS track):")
        print(f"  ║    release_location      : lat={cand.release_location.lat}, lon={cand.release_location.lon}")
        print(f"  ║    release_time_utc      : {cand.release_time_utc.isoformat()}")
        print(f"  ║    observation_time_utc  : {cand.observation_time_utc.isoformat()}")
        print(f"  ║    Contract OK           : release_time_utc <= observation_time_utc → "
              f"{'✓' if cand.release_time_utc <= cand.observation_time_utc else '✗ VIOLATION'}")
        print(f"  ║    Selection rule        : {cand.explanation}")
        print(f"  ║")
        print(f"  ║  ForwardSimulationRequest (for POST /forward):")
        fr = cand.forward_request
        forward_dict = {
            "incident_id": fr.incident_id,
            "vessel_mmsi": fr.vessel_mmsi,
            "release_location": {"lat": fr.release_location.lat, "lon": fr.release_location.lon},
            "release_time_utc": fr.release_time_utc.isoformat(),
            "observation_time_utc": fr.observation_time_utc.isoformat(),
        }
        for line in json.dumps(forward_dict, indent=4).split("\n"):
            print(f"  ║    {line}")
        print(f"  ╚══════════════════════════════════════════════════════════════════")

    # -----------------------------------------------------------------------
    # 6. Contract Validation Summary
    # -----------------------------------------------------------------------
    _sep("CONTRACT VALIDATION SUMMARY")
    all_ok = True
    for cand in response.top_candidates:
        contract_ok = cand.release_time_utc <= cand.observation_time_utc
        if not contract_ok:
            all_ok = False
        print(
            f"  MMSI {cand.vessel_mmsi}  release_time_utc <= observation_time_utc : "
            f"{'PASS ✓' if contract_ok else 'FAIL ✗'}"
        )

    print()
    if all_ok:
        print("  All forward-request contracts satisfied. Ready for POST /forward.")
    else:
        print("  WARNING: One or more forward-request contracts violated!")
    _sep()


if __name__ == "__main__":
    run()
