# OilSpill-detect — OilTrace

**Satellite oil-spill detection + AIS vessel attribution** · SIH 2026 · Problem Statement SIH26143 (NTRO) · Team AlgoRise

> [!IMPORTANT]
> **If a deployed service stops responding:** the backend and ML service run on Modal's free tier, whose monthly compute credits can run out. If requests hang or fail even after the cold-start wait (~40 s), the credit limit has most likely been reached — the code is unaffected, and every component can still be run locally (see the setup instructions below) or redeployed once credits reset.

## 🔗 Live Deployments

| Service | Status | URL |
|---|---|---|
| Frontend | 🟢 Deployable (Vercel) | `frontend/` — serves the canonical run, needs no backend |
| Backend API | 🔴 Modal workspace disabled | https://vscimatic999--oiltrace-backend-web.modal.run/api/v1 |
| Backend Swagger | 🔴 Unavailable | https://vscimatic999--oiltrace-backend-web.modal.run/docs |
| ML Detection | 🔴 Modal workspace disabled | https://vscimatic999--oiltrace-detection-web.modal.run |

> The Modal-hosted backend and ML service are currently unreachable: the workspace
> is disabled, so both return `404`. The code is unaffected and both run locally
> (see below). The frontend is unaffected either way, because the deployed build
> serves the canonical run rather than calling the API.

## What OilTrace Does

OilTrace follows a slick from satellite detection to probable vessel attribution:

```text
Sentinel-1 SAR
     ↓
ML Detection (U-Net)
     ↓
Detected Slick Polygon
     ↓
OpenDrift Hindcast
     ↓
Probable Source Region + Release Window
     ↓
AIS Vessels
     ↓
Attribution / Evidence Ranking
     ↓
Forward Simulation
     ↓
Counterfactual Comparison
```

The system combines remote-sensing evidence, ocean physics and AIS vessel movement to identify vessels that are spatially and temporally compatible with an oil spill.

## Backend API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Backend health |
| `GET /health/ml` | ML service health + warm-up |
| `POST /hindcast` | OpenDrift backward simulation |
| `GET /vessels` | AIS vessel query |
| `POST /attribute` | Rank candidate vessels |
| `POST /forward` | Forward oil-drift simulation |
| `POST /counterfactual` | Compare predicted and observed slick |
| `GET /replay/{id}` | Demo replay |

Interactive API documentation:

https://vscimatic999--oiltrace-backend-web.modal.run/docs

## 🧪 Test the Complete Backend Flow

The canonical scenario is **`incident-mediterranean-001`** in the Eastern
Mediterranean, observed at **`2024-08-26T12:00:00Z`** (Sentinel-1 scene
`Oil/00067`). Run the backend locally first (see *Run the Backend*), then:

### 1. Health

```bash
B="http://localhost:8000/api/v1"

curl -s "$B/health"
```

### 2. Hindcast

The observed slick is centred at `35.63533°N, 34.87040°E`, covering about
`266.9 km²` at ML confidence `0.768`.

```bash
curl -s -X POST "$B/hindcast" \
  -H "Content-Type: application/json" \
  --data @- <<'JSON'
{
  "slick": {
    "id": "incident-mediterranean-001",
    "timestamp_utc": "2024-08-26T12:00:00Z",
    "centroid": { "lat": 35.63533, "lon": 34.87040 },
    "geometry": {
      "type": "Polygon",
      "coordinates": [[
        [34.765, 35.558],
        [34.949, 35.558],
        [34.949, 35.742],
        [34.765, 35.742],
        [34.765, 35.558]
      ]]
    },
    "area_km2": 266.926,
    "confidence": 0.768,
    "sensor": "SAR",
    "scene_id": "Oil/00067"
  },
  "duration_hours": 6
}
JSON
```

Returns a probable source region centred near **35.61349°N, 34.82728°E** with a
release window of **06:00–12:00 UTC**. The `0.95` on the region is KDE density
mass, *not* a calibrated probability that the source lies inside it.

### 3. Vessels

```bash
curl -s "$B/vessels?bbox=33.5,34.5,36.0,36.5&start=2024-08-25T00:00:00Z&end=2024-08-26T18:00:00Z"
```

Three synthetic AIS vessels:

```text
211000001  MT CYPRUS SUN    (Tanker)
211000002  MV LEVANT STAR   (Cargo)
211000003  FV KARPASIA      (Fishing)
```

### 4. Attribution

`/attribute` takes the `source_region` from `/hindcast` and the complete vessel
objects from `/vessels`.

```json
{
  "incident_id": "incident-mediterranean-001",
  "source_region": "<source_region from /hindcast>",
  "vessels": "<response from /vessels>",
  "uncertainty_radius_km": 10.0
}
```

Ranking:

```text
#1  211000001  MT CYPRUS SUN    74.15   High
#2  211000002  MV LEVANT STAR   52.36   Medium
```

Each candidate carries a ready-to-use `forward_request` whose
`release_location` is a real AIS position, never a synthesised point.

### 5. Forward

Send a candidate's `forward_request` to `POST /forward`. This runs the forward
OpenDrift simulation from that vessel's attributed release state.

### 6. Counterfactual

Feed the forward result to `POST /counterfactual` to compare it against the
observed slick. On the canonical run:

| Candidate | Predicted oil inside slick | Centroid offset | Reaches slick |
|---|---|---|---|
| MT CYPRUS SUN | 100% | 3.79 km | yes |
| MV LEVANT STAR | 6% | 13.67 km | no |
| FV KARPASIA | untestable | — | no AIS in the release window |

That separation is produced by the physics, not by the scorer: the same
attribution engine proposed both candidates.

### 7. Replay

```bash
curl -s "$B/replay/incident-mediterranean-001"
```

The canonical replay contains **37 frames** at 30-minute intervals, spanning
2024-08-25T18:00Z to 2024-08-26T12:00Z.

## 🌊 OpenDrift

The backend uses OpenDrift/OpenOil for oil trajectory modelling.

For the canonical Eastern Mediterranean scenario the environmental forcing is
CMEMS Mediterranean Sea Physics currents and ERA5 10 m wind, covering the
demonstration window around 25–26 August 2024.

The hindcast starts from the observed slick and integrates particles backward through the environmental forcing to estimate where and when the oil could have originated.

The forward stage then tests the opposite direction: starting from the reconstructed release conditions and simulating where the oil would travel.

## 🛰️ ML Detection

The ML service uses a U-Net model for Sentinel-1 SAR oil-spill segmentation.

Demo detection:

```bash
curl -s "https://vscimatic999--oiltrace-detection-web.modal.run/detect/demo"
```

For uploaded georeferenced Sentinel-1 imagery:

```text
POST /detect
```

The service returns GeoJSON slick polygons with area and confidence.

## 🖥️ Run the Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # opendrift pulls heavy deps; allow several minutes
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Swagger is then at `http://localhost:8000/docs`. Full setup notes, including the
environmental forcing files the hindcast needs, are in `backend/README.md`.

## 🖥️ Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

`.env.development` already points at `http://localhost:8000`, so a local backend
is picked up automatically. To target a different API, set `VITE_API_BASE_URL`.

Workflow:

**Detection → Hindcast → Attribution → Forward / Counterfactual → Reset**

### Data source

A production build serves the canonical run from `src/data/canonicalRun.json`
instead of recomputing it, so a public audience cannot exhaust metered compute.
Those are verbatim backend responses recorded from a full live pass; no value in
that file is authored by hand. Development builds call the backend as normal.

| URL | Behaviour |
|---|---|
| default | production replays the canonical run; development calls the backend |
| `?mode=live` | always call the backend |
| `?mode=demo` | always replay the canonical run |

The choice persists per browser.

### Deploy the frontend on Vercel

The frontend is a static Vite build in a subdirectory, so point Vercel at
`frontend/` and let it build from there.

1. **New Project → Import** this repository.
2. Set **Root Directory** to `frontend`. This is the only required setting; it
   makes every command below run inside that folder.
3. Framework preset resolves to **Vite**; build `npm run build`, output `dist`.
   `frontend/vercel.json` already pins these, including the SPA rewrite.
4. **Deploy.** No environment variables are needed: a production build serves the
   canonical run and never calls the API.

Only `frontend/` is built; `backend/` and `ML-service/` are ignored. To point a
deployment at a live API instead, set `VITE_API_BASE_URL` in Vercel's
environment variables and open the site with `?mode=live`.

## ⚠️ Notes

- AIS data in the demonstration is **synthetic** and SIH-permitted.
- Attribution scores are **evidence/compatibility scores**, not probabilities of guilt.
- A vessel ranked first is a **candidate/suspect**, not a proven culprit.
- The canonical demonstration is a single Eastern Mediterranean incident; detection, hindcast, attribution and the counterfactual all run on that one scene.
- The source region is an uncertainty region derived from the simulated particle distribution. Its `0.95` is KDE density mass, not a probability that the true source lies inside it.
- A strong counterfactual result raises support for a candidate. It does not prove responsibility.

## 📁 Repository Structure

```text
├── ML-service/   # Sentinel-1 U-Net detection
├── backend/      # FastAPI + OpenDrift + AIS attribution
├── frontend/     # React + Leaflet investigation dashboard
└── README.md
```

Detailed live-demo requests are available in:

```text
backend/docs/SHOWCASE.md
```
