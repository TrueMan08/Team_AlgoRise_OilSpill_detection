# OilTrace — Frontend (Team AlgoRise · SIH 2026 · SIH26143)

React + Leaflet investigation dashboard for the OilTrace marine spill
intelligence system. Consumes the OilTrace FastAPI backend; contains **no**
analytical logic of its own — every score, region, trajectory and verdict is
rendered from backend responses.

## Run

```bash
npm install
cp .env.example .env        # set VITE_BACKEND_BASE_URL (default: http://127.0.0.1:8000)
npm run dev                 # http://localhost:5173
```

## The investigation workflow (all API-driven)

1. **Detection** — observed slick (Norway demo scenario ships with real
   Sentinel-1 SAR imagery, labeled as demo data)
2. **Hindcast** — `POST /api/v1/hindcast` (investigator-selectable lookback) →
   probable source region + backward trajectory
3. **Vessels** — `GET /api/v1/vessels` (bbox from source region, window ±12 h)
4. **Attribution** — `POST /api/v1/attribute` → ranked candidates + evidence
5. **Forward simulation** — `POST /api/v1/forward` using the candidate's
   prebuilt `forward_request`
6. **Counterfactual** — `POST /api/v1/counterfactual` → geometric consistency
   evidence + investigation summary

Timeline animation uses the backend's exact `trajectory_timestamps_utc` —
the frontend never generates its own timestamps.

## Language rules (enforced in UI copy)

Probable source region · attribution/compatibility score · estimated release ·
predicted footprint · geometric consistency evidence. Never: "culprit",
"confirmed source", "probability the vessel caused the spill". Behavioural
anomaly detection is labeled **not currently enabled** (deferred from MVP).

## Norway demo scenario

Deterministic end-to-end scenario (synthetic AIS, clearly labeled). The demo
slick is placed to be physically self-consistent with the bundled forcing
data: a forward OpenDrift run from the demo tanker's track lands its footprint
where the slick is observed — so the counterfactual stage shows genuine,
backend-computed geometric agreement. Default demo lookback: 2 h.

## Credits

SAR imagery: Trujillo-Acatitla et al., Zenodo (CC-BY 4.0) · Basemap: Esri
Ocean (Esri, GEBCO, NOAA, Garmin) · Map engine: Leaflet.
