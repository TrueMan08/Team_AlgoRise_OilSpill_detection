# OilSpill-detect — OilTrace

**Satellite oil-spill detection + AIS vessel attribution** · SIH 2026 · Problem Statement SIH26143 (NTRO) · Team AlgoRise

## 🔗 Live deployments

| Service | Status | URL |
|---|---|---|
| **Backend API** (hindcast · vessels · attribution · forward · counterfactual) | 🟢 Live on Modal | https://vscimatic999--oiltrace-backend-web.modal.run/api/v1 — [interactive docs](https://vscimatic999--oiltrace-backend-web.modal.run/docs) · [health](https://vscimatic999--oiltrace-backend-web.modal.run/api/v1/health) |
| **ML detection service** (Sentinel-1 U-Net) | 🟢 Live on Modal | https://vscimatic999--oiltrace-detection-web.modal.run — [health](https://vscimatic999--oiltrace-detection-web.modal.run/health) · [demo detection](https://vscimatic999--oiltrace-detection-web.modal.run/detect/demo) |
| **demo-frontend** (investigation dashboard) | 🟡 Demo — runs locally for now | see [`demo-frontend/`](demo-frontend/) below |

> Free-tier cold start: the first request after ~5 idle minutes takes 20–40 s extra — hit the health links above ~1 min before demoing.

OilTrace answers one question end to end: *a slick was spotted on satellite radar — which vessel most plausibly released it?* A SAR scene goes through ML detection, ocean-physics backtracking reconstructs where the oil came from, AIS records surface the vessels that were there, an evidence engine ranks them, and a forward "counterfactual" simulation tests the top suspect's release against the observed slick.

```
Sentinel-1 SAR scene
   │  ML-service (U-Net)                    ── deployed on Modal
   ▼
Detected slick polygon (GeoJSON)
   │  backend /hindcast (OpenDrift)         ── deployed on Modal
   ▼
Probable source region + release window
   │  backend /vessels → /attribute
   ▼
Ranked candidate vessels (evidence scores)
   │  backend /forward → /counterfactual
   ▼
Physical-consistency verdict (Jaccard overlap, trajectory intersection)
   │
   ▼
demo-frontend — interactive investigation dashboard
```

---

## `backend/` — analysis API (deployed ✅)

FastAPI service that owns all the physics and reasoning. **Live on Modal:**
**https://vscimatic999--oiltrace-backend-web.modal.run/api/v1** ([interactive docs](https://vscimatic999--oiltrace-backend-web.modal.run/docs); warm it with `GET /health/ml` before demos — free-tier cold start is ~20–40 s).

| Endpoint | What it does |
|---|---|
| `GET /health` · `/ping` · `/health/ml` | Liveness + ML-service reachability (also warms it) |
| `POST /detect` | Proxies a Sentinel-1 GeoTIFF to the ML service, returns slicks ready for hindcast |
| `POST /hindcast` | Real OpenDrift **backward** simulation from the observed slick → probable source region (95 % probability mass) + release window + backward trajectory |
| `GET /vessels` | Synthetic AIS query by bbox + time window (SIH-permitted synthetic data, always labeled) |
| `POST /attribute` | Evidence engine: spatial / temporal / trajectory compatibility + AIS reliability → ranked candidates with a pre-built `forward_request` for the top suspect |
| `POST /forward` | OpenDrift **forward** simulation from the estimated release → predicted footprint |
| `POST /counterfactual` | Compares predicted footprint vs observed slick: Jaccard overlap, trajectory intersection, centroid distance, evidence strength |
| `GET /replay/{id}` | Cached frame-by-frame replay of the canonical demo incident |

Ships with the North Sea demo forcing data (`data/currents.nc`, `wind.nc`; window 4–6 °E, 59–61 °N, 20–22 Aug 2025), 174 passing tests, and `docs/SHOWCASE.md` — a live-verified curl sequence for the full chain (tanker ranked #1 at 98.1/100).

## `ML-service/` — SAR detection (deployed ✅)

U-Net oil-spill segmentation on Sentinel-1 imagery. **Live on Modal:**
**https://vscimatic999--oiltrace-detection-web.modal.run**

- `service/` — the deployable API (FastAPI + Dockerfile): upload a 2-band (VV+VH) georeferenced GeoTIFF ≤ 80 MB to `POST /detect`, get GeoJSON slick polygons with area + confidence; `GET /detect/demo` returns a precomputed real detection (266.9 km² Mediterranean slick) instantly.
- `ml/` — training & evaluation code: model, data loaders, metrics, threshold/TTA sweeps.
- `manifests/` — dataset manifests for the Zenodo oil-spill dataset (450 pixel-verified scenes).
- `runs/` — experiment records (configs + metric histories). Weight binaries are excluded; the deployed **E5_focal** checkpoint is baked into the Modal image.

## `demo-frontend/` — investigation dashboard (demo, not deployed yet)

React + Leaflet dashboard that drives the whole pipeline through the backend APIs — currently the **demo build**: run locally, ships with the deterministic Norway scenario (real SAR imagery, synthetic AIS, live backend computation for every analytical value).

- Six-stage guided workflow: Detection → Hindcast → Vessels → Attribution → Forward Simulation → Counterfactual
- OpenDrift-style drift particle animation (backtrack reconstruction + released-oil cloud) with smooth timeline playback on the backend's own timestamps
- Honest-language guardrails throughout: scores are compatibility evidence, never "probability of guilt"; synthetic AIS is always labeled

```bash
cd demo-frontend
npm install
cp .env.example .env   # VITE_BACKEND_BASE_URL → Modal backend URL, or http://127.0.0.1:8000
npm run dev            # http://localhost:5173 → "Launch Norway Demo Scenario"
```

---

## Try the deployed chain in 60 seconds

```bash
B=https://vscimatic999--oiltrace-backend-web.modal.run/api/v1
curl $B/health                       # wake the backend
curl "$B/replay/incident-norway-001" # 37-frame canonical incident replay
```

Full request bodies for hindcast → vessels → attribute → forward → counterfactual are in `backend/docs/SHOWCASE.md` (every step live-verified, all endpoints returning 200).

**Honesty notice:** all AIS data is synthetic (SIH-permitted). Model outputs are spatial, temporal and physical-consistency **evidence** — never proof of vessel responsibility.
