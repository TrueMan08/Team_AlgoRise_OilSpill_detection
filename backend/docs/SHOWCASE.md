# OilTrace — Canonical Showcase Incident (`incident-norway-001`)

The one incident where the ENTIRE chain runs live, end to end.
Base URL: `https://vscimatic999--oiltrace-backend-web.modal.run/api/v1`
(Warm up first: `GET /health/ml` ~1 min before demoing. Every step below
was live-verified 31 Aug 2026.)

## The story
A 20 km² slick is observed at **60.044°N 4.482°E, 2025-08-20T12:00Z**
(North Sea, off Norway). Backward drift physics reconstructs the source;
AIS filtering finds three vessels; evidence scoring identifies the tanker.

## 1. Hindcast — real OpenDrift, ~20 s
```bash
curl -X POST $B/hindcast -H "Content-Type: application/json" -d '{
  "slick": {"id":"slick-norway-001","timestamp_utc":"2025-08-20T12:00:00Z",
    "centroid":{"lat":60.044,"lon":4.482},
    "geometry":{"type":"Polygon","coordinates":[[[4.43,60.0],[4.53,60.0],[4.53,60.09],[4.43,60.09],[4.43,60.0]]]},
    "area_km2":20.0,"confidence":0.8,"sensor":"Sentinel-1 SAR"},
  "duration_hours": 3}'
```
→ source region centroid **(60.065, 4.474)**, release window
**09:00→12:00Z**, aligned backward trajectory.

## 2. Vessels
```bash
curl "$B/vessels?bbox=4.0,59.0,6.0,61.0&start=2025-08-19T12:00:00Z&end=2025-08-20T14:00:00Z"
```
→ 3 candidates: tanker 678901234, cargo 789012345, fisher 890123456.

## 3. Attribute — pass the hindcast `source_region` + the vessels
→ **#1 suspect: tanker 678901234, score 98.1/100** (crossed the source at
~09:26Z, inside the window). Cargo ranks 2nd (right time, ~12 km north);
fisher eliminated on temporal mismatch. `no_strong_candidate: false`.
Response includes a pre-built `forward_request` for the top suspect.

## 4. Forward counterfactual
POST the top candidate's `forward_request` to `$B/forward`
→ simulated release drifts to the observed slick (11-point trajectory).

## 5. Replay — for the frontend timeline
```bash
curl "$B/replay/incident-norway-001"
```
→ **37 frames** (30-min interval, 19 Aug 18:00Z → 20 Aug 12:00Z): vessels
animate along tracks, source region appears as `reconstructed` during the
window, slick flips to `observed` at detection time.

## Detection (shown separately — Mediterranean scene)
Real Sentinel-1 detection stays its own act:
`GET /detect/demo` on the ML service (instant) or `POST /detect` — the
real 266.93 km² slick. Geography note: forcing data only covers Norway,
so detection's Mediterranean scene cannot feed this hindcast; unifying on
one real Mediterranean incident (new CMEMS subset + re-centred AIS) is the
documented post-showcase upgrade.

*Synthetic-data notice: all AIS is synthetic (SIH-permitted); scores are
relative attribution scores, not probabilities; candidates are "suspects",
never "culprits".*
