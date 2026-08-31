# OilSpill-detect — OilTrace

**Satellite oil-spill detection + AIS vessel attribution** · SIH 2026 · Problem Statement SIH26143 (NTRO) · Team AlgoRise

> [!IMPORTANT]
> **If a deployed service stops responding:** the backend and ML service run on Modal's free tier, whose monthly compute credits can run out. If requests hang or fail even after the cold-start wait (~40 s), the credit limit has most likely been reached — the code is unaffected, and every component can still be run locally (see the setup instructions below) or redeployed once credits reset.

## 🔗 Live Deployments

| Service | Status | URL |
|---|---|---|
| Backend API | 🟢 Live on Modal | https://vscimatic999--oiltrace-backend-web.modal.run/api/v1 |
| Backend Swagger | 🟢 Live | https://vscimatic999--oiltrace-backend-web.modal.run/docs |
| ML Detection | 🟢 Live on Modal | https://vscimatic999--oiltrace-detection-web.modal.run |
| Frontend | 🟡 Local demo | `demo-frontend/` |

> Free-tier services may have a cold start. Run `GET /health/ml` before a demo.

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

The canonical live scenario is **`incident-norway-001`**.

### 1. Health

```bash
B="https://vscimatic999--oiltrace-backend-web.modal.run/api/v1"

curl -s "$B/health"
curl -s "$B/health/ml"
```

### 2. Hindcast

The canonical slick is at `60.044°N, 4.482°E`, observed at `2025-08-20T12:00:00Z`.

```bash
curl -s -X POST "$B/hindcast" \
  -H "Content-Type: application/json" \
  --data '{
    "slick": {
      "id": "slick-norway-001",
      "timestamp_utc": "2025-08-20T12:00:00Z",
      "centroid": {
        "lat": 60.044,
        "lon": 4.482
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [4.43, 60.00],
          [4.53, 60.00],
          [4.53, 60.09],
          [4.43, 60.09],
          [4.43, 60.00]
        ]]
      },
      "area_km2": 20.0,
      "confidence": 0.8,
      "sensor": "Sentinel-1 SAR"
    },
    "duration_hours": 3
  }'
```

Verified result: source around **60.0651°N, 4.4735°E**, with a release window of **09:00–12:00 UTC**.

### 3. Vessels

```bash
curl -s \
  "$B/vessels?bbox=4.0,59.0,6.0,61.0&start=2025-08-19T12:00:00Z&end=2025-08-20T14:00:00Z"
```

The canonical scenario returns three synthetic AIS vessels:

```text
678901234
789012345
890123456
```

### 4. Attribution

`/attribute` uses the `source_region` returned by `/hindcast` and the complete vessel objects returned by `/vessels`.

Request shape:

```json
{
  "incident_id": "incident-norway-001",
  "source_region": "<source_region from /hindcast>",
  "vessels": "<response from /vessels>",
  "uncertainty_radius_km": 10.0
}
```

Verified ranking:

```text
#1  678901234  — 98.125
#2  789012345  — 60.579
```

The top candidate contains a ready-to-use `forward_request`.

### 5. Forward

Send the `forward_request` from the top `/attribute` candidate to:

```text
POST /forward
```

This performs the forward OpenDrift simulation from the reconstructed release conditions.

### 6. Counterfactual

Use the forward result with:

```text
POST /counterfactual
```

This compares the simulated result with the observed slick using physical-consistency metrics such as trajectory intersection, centroid distance and footprint overlap.

The exact request schema is available in Swagger.

### 7. Replay

```bash
curl -s "$B/replay/incident-norway-001"
```

The canonical replay contains **37 frames** and the same three Norway vessels.

## 🌊 OpenDrift

The backend uses OpenDrift/OpenOil for oil trajectory modelling.

For the canonical Norway scenario, the bundled environmental forcing covers approximately:

```text
59–61°N
4–6°E
20–22 August 2025
```

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

## 🖥️ Run the Frontend

```bash
cd demo-frontend
npm install
cp .env.example .env
npm run dev
```

Set:

```text
VITE_BACKEND_BASE_URL=https://vscimatic999--oiltrace-backend-web.modal.run/api/v1
```

Workflow:

**Detection → Hindcast → Vessels → Attribution → Forward → Counterfactual**

## ⚠️ Notes

- AIS data in the demonstration is **synthetic** and SIH-permitted.
- Attribution scores are **evidence/compatibility scores**, not probabilities of guilt.
- A vessel ranked first is a **candidate/suspect**, not a proven culprit.
- The canonical physics demo uses Norway because the deployed environmental forcing covers that region and time.
- The ML demo detection is a separate real Mediterranean scene; running physics on it would require Mediterranean forcing data.

## 📁 Repository Structure

```text
├── ML-service/       # Sentinel-1 U-Net detection
├── backend/          # FastAPI + OpenDrift + AIS attribution
├── demo-frontend/    # React + Leaflet investigation dashboard
└── README.md
```

Detailed live-demo requests are available in:

```text
backend/docs/SHOWCASE.md
```
