# OilTrace Backend — CONTEXT BRAIN

> **Read this FIRST.** This file brings any AI agent (or new human) to the
> project's current working state without re-deriving it. After reading it,
> read `HANDOFF_LOG.md` for what changed since — and **append your own entry
> there after every piece of work, before pushing**.
>
> Claim discipline (inherited from the ML module, applies here too): label
> facts as **MEASURED / PROVEN / PROPOSED / EXPERIMENT / LIMIT**. Never
> silently convert a proposal into a fact.

---

## 1. Project identity

- **Competition:** Smart India Hackathon 2026, Problem Statement **SIH26143**
  (NTRO) — detect marine oil spills in satellite SAR imagery, hindcast the
  slick to its origin, and rank suspect vessels from AIS data.
- **System name:** OilTrace · **Team:** AlgoRise
- **This repo:** the backend / orchestration layer (Parth's module) — a
  FastAPI **modular monolith** that ties the five pipeline stages together.

### Team module map

| Person | Module | Where it lives |
|---|---|---|
| Satyam | SAR+ML detection | Separate repo `Satyam087/CodeRabbit` → `service/`; **deployed** (see §4) |
| Ved | Ocean drift / hindcast (OpenDrift) | `app/services/hindcast.py` — **LIVE** (backward + forward) |
| Nimit | AIS + attribution scoring | `app/services/vessels.py`, `app/services/attribution.py` — **stubs** |
| Parth | This backend: contracts, orchestration | everything here |
| Sayan | Frontend GIS (React/Leaflet) | separate repo (consumes this API) |
| Agrima | Presentation / 6-slide SIH deck | not in code |

## 2. Architecture (as built)

```text
Frontend (Sayan)
   │  HTTPS /api/v1/*
   ▼
FastAPI modular monolith (this repo)
   ├── POST /detect      → proxies the deployed ML service → list[Slick]
   ├── POST /hindcast    → backward OpenOil drift → SourceRegion + trajectory
   ├── POST /forward     → forward counterfactual  → trajectory + footprint
   ├── GET  /vessels     → (stub) AIS query/filter          → Vessel tracks
   ├── POST /attribute   → (stub) 0.35/0.30/0.20/0.15 score → Attribution
   └── GET  /replay/{id} → (stub) timeline for the UI       → Replay
```

- App factory: `app/main.py` (CORS, lifespan, `/docs`, `/redoc`)
- Router: `app/api/v1/api.py` → `app/api/v1/endpoints/*`
- Each endpoint delegates to `app/services/*` — services hold the logic
- Contracts: `app/models/*` — Pydantic v2, strict (see §3)
- Settings: `app/core/config.py` (pydantic-settings, `.env`)
- Tests: `tests/` — pytest; **every contract change needs its tests
  updated; the suite must pass before any push** (131/131 as of 30 Aug)

## 3. Contracts — the non-negotiables

All defined in `app/models/`; full walkthrough in `Complete_Flow.md` and
per-object docs in `docs/*.docx`.

- **Geometry** (`geometry.py`): GeoJSON RFC 7946, coordinates are
  **[longitude, latitude]**; `GeoJSONGeometry = Polygon | MultiPolygon`
  (discriminated union); rings must be closed, ≥4 points. `Point` is a
  named `{lat, lon}` object.
- **Timestamps** (`validation.py`): `UTCDateTime` **rejects naive
  datetimes** — everything is timezone-aware UTC.
- **Slick** (`slick.py`): `id, timestamp_utc, centroid, geometry,
  area_km2 ≥ 0, confidence ∈ [0,1], sensor?, scene_id?`
- **SourceRegion** (`source_region.py`): ≥1 `SourceCandidateRegion`,
  unique candidate ids — this is what Ved's hindcast must produce.
- **SatelliteScene** (`satellite_scene.py`): scene metadata incl.
  `acquired_at_utc` — the intended home of sensing time (see §4 caveat).
- Vocabulary: "suspect / candidate / attribution confidence" — never
  "culprit"; scores are **relative scores, not probabilities**.

## 4. The ML detection service (deployed, live) — MEASURED facts

- **URL:** `https://vscimatic999--oiltrace-detection-web.modal.run`
  (Modal free tier, scales to zero; **cold start +20–40 s**, inference
  ~20–60 s/scene on CPU; warm it via `GET /health` or this repo's
  `GET /api/v1/health/ml` before demos)
- **Full API reference:** `docs/OilTrace_Detection_API.md` (in this repo)
- **Model:** `E5_focal` U-Net (Focal+Dice fine-tune). Validation (scene-level
  held-out, INCLUDING look-alike hard negatives): pixel Dice 0.350, object
  precision 0.471, recall(≥10 ha) 0.667, median centroid error ~85 m.
  Best classical baseline on the same data: Dice 0.063.
- **Postprocessing frozen from validation:** threshold 0.325, min slick
  250 px, min confidence 0.60. The Part III test set is **SEALED** — one
  evaluation at the very end; never call the service on Part III scenes to
  compute aggregate statistics.
- **LIMIT — no sensing time:** the dataset's TIFFs carry no acquisition
  timestamp; `Slick.timestamp_utc` must be injected by this backend
  (`acquired_at_utc` form field on `/detect`; processing time is the demo
  fallback). For the cached demo bundle, fix one agreed timestamp.
- **LIMIT — look-alikes:** a minority of very dark look-alike regions still
  produce confident false positives; confidence 0.60–0.70 detections should
  be displayed as "uncertain" in the UI.

## 5. Current state (30 Aug 2026)

- `main`: contracts + endpoint/service stubs + API docs. All tests green.
- **`feature/ml-integration`** (pushed, awaiting Parth's review):
  `/detect` fully wired to the live ML service and **E2E verified**
  (demo scene → 1 Slick, 266.928 km², conf 0.768, 37.6 s round trip).
  Introduces: `list[Slick]` response, `acquired_at_utc` form field,
  async service, `GET /health/ml`, `ML_SERVICE_URL`/`ML_SERVICE_TIMEOUT`
  settings, +5 adapter tests (suite: 100/100).
- **Next build order (PROPOSED):** merge ml-integration → ~~Ved implements
  `run_hindcast`~~ **DONE** → Nimit's synthetic AIS + filter (150 km / ±12 h /
  ≥3 pts / 30-min gap split) + weighted score (0.35 spatial / 0.30 temporal /
  0.20 trajectory / 0.15 AIS-reliability; `no_strong_candidate` < 0.40) →
  replay assembly → **cached demo bundle** (frozen incident JSON so the
  judged demo never depends on live calls).

### 5.1 Ved's drift integration (30 Aug 2026) — MEASURED

- **Backward hindcast:** `POST /hindcast` → `run_hindcast()` — seeds
  from `Slick.centroid` via `seed_elements()`, runs OpenOil backward,
  extracts per-timestep centroid trajectory, computes Gaussian KDE on
  final-time particle positions with local metric projection (centered
  on **particle mean**, NOT ground truth), extracts 95% HDR contour →
  `SourceCandidateRegion` (geometry + centroid + time window +
  probability as **KDE density mass fraction**).
- **Forward counterfactual:** `POST /forward` → `run_forward()` — seeds
  from `release_location` (provided by Nimit's future attribution),
  runs OpenOil forward to `observation_time_utc`, extracts trajectory +
  convex hull predicted particle envelope.
- **Real integration test results:**
  - Backward: 100 particles, 6h, 6.3s runtime, 7 trajectory points,
    valid Polygon geometry, probability=0.95.
  - Forward: 100 particles, 6h, 6.2s runtime, 7 trajectory points,
    valid Polygon footprint.
- **Scientific caveat:** `SourceCandidateRegion.probability` is a KDE
  density mass fraction (0.95 = 95% HDR), NOT a calibrated probability.
  `predicted_footprint` is a simulated particle envelope, NOT an
  observed oil footprint.
- **Dependencies added:** opendrift 1.14.11, scipy, shapely, matplotlib
  (headless contour extraction), xarray, netCDF4, cartopy, geopandas.
- **Forcing data:** NetCDF current + wind files, configured via
  `DRIFT_FORCING_*_PATH` env vars.  Test data covers lon [4,6],
  lat [59,61], time 2025-08-20 to 2025-08-22.
- **Configuration:** 11 `DRIFT_*` settings in `app/core/config.py`
  (particle count, oil type, timestep, KDE grid, HDR fraction, etc.).
- **Nimit handoff:** `HindcastResponse` provides `SourceRegion` +
  backward trajectory + timestamps.  Nimit filters AIS within the
  source region geometry and time window.
- **Sayan handoff:** all trajectory/geometry data is GeoJSON-ready,
  no xarray/NetCDF/scipy knowledge required.

## 6. Working rules for agents in this repo

1. **Read `HANDOFF_LOG.md` after this file** — it is the delta since this
   brain was written. The newest entries are at the TOP.
2. **Log before you push.** Every change gets a HANDOFF_LOG entry (format
   in that file) in the same commit or the same push.
3. **Contracts are load-bearing.** Changing any `app/models/*` field is a
   cross-team event — flag it in the log's `BREAKING` field and tell the
   affected owner.
4. **Tests gate pushes.** `python -m pytest tests -q` must be 100% green.
5. **Don't touch other people's stubs without noting it** — hindcast/
   vessels/attribution bodies belong to Ved and Nimit.
6. **No secrets in git.** Config via `.env` (see `.env.example`).
7. **Don't overclaim** — the PPT/demo language rules (no "first", no
   "culprit", no "exact origin") apply to API descriptions and docs too.

## 7. Pointers

- ML module repo (training, experiments, deployment): `Satyam087/CodeRabbit`
  — its own context pair lives there (`Context/OilTrace_SIH26143_Context_Brain.md`
  + `OilTrace_Victus_Handoff.md`).
- End-to-end flow narrative: `Complete_Flow.md`
- ML API + contract mapping: `docs/OilTrace_Detection_API.md`
- SAR data credit (required on anything public): Trujillo-Acatitla et al.,
  Zenodo, CC-BY 4.0.
