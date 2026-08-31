# HANDOFF LOG — OilTrace Backend

> **Protocol for every AI agent (and human) working in this repo:**
>
> 1. **Before doing anything:** read `CONTEXT_BRAIN.md`, then this log
>    top-to-bottom until you reach entries you already know.
> 2. **After doing anything, BEFORE pushing:** append an entry at the
>    **TOP** of the table of entries below, using the exact format. The log
>    entry ships in the same push as the change it describes.
> 3. If your change alters any contract in `app/models/*`, set
>    `BREAKING: yes` and name the affected module owner.
> 4. A push without a log entry is a protocol violation — fix it with a
>    follow-up entry immediately.

## Entry format (copy this template)

```markdown
### YYYY-MM-DD HH:MM IST · <agent-or-person> · branch <name>
- **What:** one line per change (files touched)
- **Why:** the reason / the request it served
- **Verified:** how (tests? E2E? not verified?)
- **BREAKING:** no | yes → <which contract, who is affected>
- **Next:** what the following agent should pick up
```

---

## Entries (newest first)

### 2026-08-31 04:05 IST · Claude (for Satyam, per Ved's handoff) · branch main
- **What:** DECISION EXECUTED — **Norway is the canonical showcase incident
  (`incident-norway-001`)**, per Ved's recommendation. Added NORWAY_*
  constants (ais_sample.py), per-incident replay scenarios (Mumbai kept),
  optional `DRIFT_LANDMASK_PATH` config override, `docs/SHOWCASE.md` with
  the full live-verified demo sequence. 175/175 tests. Deployed.
- **Live full-chain verification on the deployment:** hindcast → source
  (60.065, 4.474) window 09:00–12:00Z → 3 vessels → **#1 suspect tanker
  678901234, score 98.1** → forward counterfactual (11-pt trajectory) →
  replay 37 frames. THE CHAIN WORKS IN PRODUCTION.
- **Landmask finding:** production needs NO landmask file — OpenOil's
  built-in auto-landmask works in the Linux container (multiple live runs).
  Ved's local `land_binary_mask` error is a Windows-local issue; use the
  new `DRIFT_LANDMASK_PATH` override there. `data/landmask.nc` deliberately
  NOT shipped.
- **Ved's /hindcast 500:** not reproducible — his exact payload returns 200
  in ~21 s. It was a transient Modal container loss; if seen again, retry
  once. Particle count untouched per his instruction.
- **BREAKING:** no. Sayan: showcase replay id is `incident-norway-001`.
- **Next:** frontend against SHOWCASE.md; post-showcase: converge on a real
  Mediterranean incident (CMEMS subset + AIS re-centre).

### 2026-08-31 02:40 IST · Claude (for Satyam) · branch main
- **What:** implemented the last stub — `GET /replay/{id}`: cached demo
  replay (`app/services/replay.py`) built deterministically from the
  synthetic AIS fixture per the frozen cached-demo-bundle plan. 17 frames /
  30-min interval over 26-Aug 18:00Z → 27-Aug 02:00Z; vessels observed at
  fixes and linearly interpolated between them; source geometry appears as
  `reconstructed` during the release window and `observed` at observation
  time. Unknown ids now 404 (was silent null). Endpoint gets
  `response_model=Replay`; +3 service tests; old smoke test updated.
- **Verified:** 174/174 tests pass; deployed and verified live (below).
- **BREAKING:** mild — `/replay/{unknown}` returns 404 instead of 200 null;
  the demo incident id is `incident-demo-001` (Sayan: use this id).
- **Next:** all five pipeline stages implemented; geography convergence
  remains the last demo item.

### 2026-08-31 02:05 IST · Claude (for Satyam) · branch main
- **What:** deployed the backend to Modal: added `modal_app.py`
  (4 GB / 2 CPU container, 600 s timeout for drift sims, scale-to-zero,
  forcing data bundled). **Live URL:**
  `https://vscimatic999--oiltrace-backend-web.modal.run`
- **Why:** free hosting need (Render free tier concerns); same workspace as
  the ML service. Frontend should call this base URL + `/api/v1/...`.
- **Verified LIVE:** `/api/v1/health` ok · `/api/v1/health/ml` warms both
  services · full detect chain backend→ML on Modal (266.928 km², conf
  0.768, 40 s) · **real OpenDrift hindcast in the cloud**: Norway-window
  slick (60N 5E, 2025-08-21T18Z) → source region 60.09N 4.96E with
  release window, 7-point aligned trajectory, **18.8 s**.
- **BREAKING:** no. Note: cold chain stacks two cold starts (~60-80 s worst
  case) — hit `/api/v1/health/ml` a minute before demos.
- **Next:** Sayan points the frontend at the URL; geography convergence
  decision (see review entry below) unlocks the single-incident full-chain
  demo.

### 2026-08-31 01:45 IST · Claude (for Satyam) · branch main (review only)
- **What:** reviewed the hindcast/attribution/vessels drop (`0201f95`..`dd75aa7`)
  end-to-end. Verified: full suite **171/171 green** (with opendrift installed);
  `run_demo.py` runs clean (needs `PYTHONIOENCODING=utf-8` on Windows);
  `HindcastRequest.slick` consumes the /detect `Slick` exactly (seeds from
  `slick.centroid`); attribution weights are the frozen 0.35/0.30/0.20/0.15
  with anomaly slot zeroed; language discipline intact. Quality: excellent.
- **⚠ THE one integration gap — geography/time must converge for the full-chain
  demo:** detection demo scene is Eastern Mediterranean (35.6N, 34.9E, no
  timestamp); bundled forcing (`data/currents.nc`, `wind.nc`) covers
  **Norway 59–61N / 4–6E, 20–22 Aug 2025**; run_demo's AIS ring is Mumbai
  (18.9N, 72.8E, Aug 2026). A real `/detect → /hindcast` chain on the demo
  slick will fail (outside forcing domain AND time range). **Recommendation:**
  converge on the Mediterranean around the real detected slick — Ved
  re-subsets CMEMS forcing for ~34–36.5E / 35–36.5N on an agreed demo date,
  Nimit re-centres the synthetic AIS there, and the team fixes ONE demo
  timestamp (which also feeds `acquired_at_utc`). Alternative: keep Norway
  and use a synthetic slick for the chain demo, showing real detection
  separately.
- **Verified:** pytest 171/171; run_demo full output; forcing coverage read
  from the NetCDF files directly.
- **BREAKING:** no (no code changed)
- **Next:** team decision on demo geography; then wire the cached demo bundle.

### 2026-08-30 19:33 IST · Claude (for Nimit) · branch main
- **What:** Implemented Nimit's AIS Reconstruction + Vessel Attribution stage.
  - **CREATED:** `app/data/__init__.py` — data package init.
  - **CREATED:** `app/data/ais_sample.py` — synthetic AIS demo dataset (5 vessels,
    ported verbatim from Nimit's previous implementation; covers strong/medium/temporal/
    spatial-eliminated/gap scenarios for Arabian Sea canonical incident).
  - **CREATED:** `app/schemas/attribution.py` — three new schemas:
    `AttributeRequest` (POST /attribute body), `CandidateReleaseState` (Nimit→Ved
    handoff: rank, score, confidence, release_location, release_time_utc,
    observation_time_utc, ForwardSimulationRequest pre-built), `AttributeResponse`
    (all_attributions + top_candidates + no_strong_candidate).
  - **MODIFIED:** `app/services/vessels.py` — replaced stub with full `get_vessels()`
    implementation (bbox filtering, chronological sort, duplicate dedup, gap detection).
  - **MODIFIED:** `app/services/attribution.py` — replaced stub with full 1000-line
    implementation: `run_attribution()` (4-component scoring: Spatial 0.35, Temporal
    0.30, Trajectory 0.20, AIS Reliability 0.15; hard filters: 150 km spatial,
    ±12 h temporal, ≥3 pts/segment, 30-min gap split; Option A EvidenceBreakdown
    mapping), `select_release_state()` (corrected polygon-distance rule, not centroid),
    `build_top_candidates()`, `run_full_attribution()`.
  - **MODIFIED:** `app/api/v1/endpoints/vessels.py` — replaced no-arg stub with typed
    GET /vessels endpoint (bbox, start, end query params; response_model=list[Vessel]).
  - **MODIFIED:** `app/api/v1/endpoints/attribution.py` — replaced no-arg stub with
    typed POST /attribute endpoint (AttributeRequest body; AttributeResponse response).
  - **MODIFIED:** `app/services/__init__.py` — added `run_full_attribution` export.
  - **MODIFIED:** `app/schemas/__init__.py` — added attribution schema exports.
  - **MODIFIED:** `requirements.txt` — added `pyproj>=3.6.0` (UTM projection).
  - **MODIFIED:** `tests/test_endpoints.py` — updated test_vessels_endpoint (now sends
    valid query params → 200) and test_attribute_endpoint (now expects 422 with no body,
    consistent with test_hindcast_endpoint pattern).
  - **CREATED:** `tests/test_vessels_service.py` — 6 vessels service tests.
  - **CREATED:** `tests/test_attribution_service.py` — 19 attribution + TOP 2 tests.
  - **MODIFIED:** `run_demo.py` — end-to-end demo: synthetic SourceRegion → AIS
    retrieval → scoring → TOP 2 → release states → forward payload validation.
- **Why:** Implement Nimit's AIS Reconstruction + Vessel Attribution stage per the
  frozen MVP spec and integration plan.
- **Verified:**
  - Full pytest suite: **157/159 passed** (2 pre-existing failures: opendrift not
    installed locally; `test_hindcast_service.py::TestMockedRunHindcast::test_run_hindcast_pipeline`
    and `test_hindcast_service.py::TestMockedRunForward::test_run_forward_pipeline` —
    both try to `patch("opendrift.models.openoil.OpenOil", ...)` but opendrift is not
    installed in the local dev environment; these are pre-existing failures unrelated to
    Nimit's module, unchanged from baseline).
  - Demo (`python3 run_demo.py`) executed successfully: 4 candidates scored, no_strong=False,
    TOP 2 selected (MMSI 123456789 score=98.12 High, MMSI 567890123 score=68.33 Medium),
    both release_time_utc ≤ observation_time_utc contracts PASS ✓.
  - Release-state rule verified: MMSI 123456789 selected lat=18.9125 at 22:15Z (inside
    window, 0.00 km to polygon); MMSI 567890123 selected lat=18.92083 at 22:45Z (inside
    window, 1.90 km to polygon). Both use real AIS coordinates.
  - EvidenceScore contribution invariant: score × weight = contribution (1e-6 tolerance)
    verified for all scored candidates.
  - ForwardSimulationRequest objects validate successfully (Pydantic model).
- **BREAKING:** yes → `GET /vessels` now requires `bbox`, `start`, `end` query params
  (was no-arg stub); `POST /attribute` now requires `AttributeRequest` JSON body
  (was no-arg stub). Affected: **Sayan** (frontend must send params to both endpoints).
- **Scientific decisions:**
  - AIS Reliability in `source_probability` slot (Option A — no model changes).
  - `ais_anomaly` = zero slot, weight=0 (behavioural ML deferred from MVP).
  - Release state uses polygon-distance, NOT centroid distance.
  - Scores are relative attribution scores, NOT probabilities.
  - Vessels with only one AIS segment of <3 points → excluded (not flagged as
    suspicious; gaps are missing evidence only).
- **Pre-existing test failures (NOT introduced by this change):**
  - `test_hindcast_service.py::TestMockedRunHindcast::test_run_hindcast_pipeline` —
    tries to mock `opendrift.models.openoil.OpenOil` but opendrift not installed locally.
  - `test_hindcast_service.py::TestMockedRunForward::test_run_forward_pipeline` —
    same cause. Both were failing before this change (baseline: 129/131 passed).
- **Note on reported baseline:** CONTEXT_BRAIN.md states 131/131 on feature/drift-integration.
  The current main has 131 tests in the baseline (129 passed + 2 failed opendrift).
  After this change: 159 total (131 original + 6 vessels + 19 attribution + updated 3
  endpoint tests) = 157 passed + 2 failed (same opendrift).
- **Next:**
  - **Sayan (frontend):** Update `/vessels` and `/attribute` API calls to include
    required parameters. Read `top_candidates[0].forward_request` and pass to `POST /forward`.
  - **Ved:** When `POST /attribute` returns `top_candidates`, forward each candidate's
    `forward_request` to `POST /forward` to run counterfactual drift simulation.
  - **Production deployment:** Replace `app/data/ais_sample.py` with a real AIS data
    source (PostGIS query or live API).

### 2026-08-30 17:45 IST · Claude (for Ved) · branch feature/drift-integration
- **What:** Implemented Ved's drift subsystem — backward hindcast and
  forward counterfactual OpenDrift/OpenOil simulation.
  - **CREATED:** `app/schemas/hindcast.py` (HindcastRequest, HindcastResponse,
    ForwardSimulationRequest, ForwardSimulationResult, SimulationMetadata).
  - **CREATED:** `tests/test_hindcast_service.py` (31 tests: schema validation,
    UTC enforcement, coordinate ordering, KDE geometry validity, trajectory/timestamp
    1:1 alignment, slick_id propagation, metric projection, mocked run_hindcast and
    run_forward execution-level tests).
  - **MODIFIED:** `app/services/hindcast.py` — replaced 4-line stub with 574-line
    production implementation: `run_hindcast()` (Slick → seed_elements → backward
    OpenOil → trajectory extraction → Gaussian KDE → 95% HDR → SourceCandidateRegion
    → SourceRegion → HindcastResponse) and `run_forward()` (ForwardSimulationRequest
    → seed_elements → forward OpenOil → trajectory → convex hull footprint →
    ForwardSimulationResult).
  - **MODIFIED:** `app/api/v1/endpoints/hindcast.py` — replaced 10-line stub with
    typed POST /hindcast and POST /forward endpoints with error handling.
  - **MODIFIED:** `app/core/config.py` — added 11 `DRIFT_*` settings (forcing paths,
    particle count, oil type, timestep, KDE parameters).
  - **MODIFIED:** `.env.example` — documented new drift settings.
  - **MODIFIED:** `app/schemas/__init__.py` — re-exports for new schemas.
  - **MODIFIED:** `app/services/__init__.py` — added `run_forward` export.
  - **MODIFIED:** `tests/test_endpoints.py` — hindcast endpoint test updated
    (200 → 422 since endpoint now requires HindcastRequest body).
  - **MODIFIED:** `CONTEXT_BRAIN.md` — updated module status, architecture,
    test count, added §5.1 with Ved's measured integration results.
- **Why:** implement Ved's portion of the oil spill attribution pipeline
  (backward drift → source region reconstruction, forward counterfactual →
  physical plausibility check).
- **Verified:**
  - Full pytest suite: **131/131 green** (100 existing + 31 new).
  - Real backward OpenDrift test: 100 particles, 6h, 6.3s — valid Polygon
    KDE geometry, probability=0.95, 7 trajectory points 1:1 with timestamps.
  - Real forward OpenDrift test: 100 particles, 6h, 6.2s — valid Polygon
    footprint, 7 trajectory points, metadata propagated.
  - OpenDrift 1.14.11 API verified: `o.result` (not `o.get_dataset()`).
  - Forcing data validated: lon [4,6], lat [59,61], time 2025-08-20 to
    2025-08-22 (currents + wind).
- **BREAKING:** yes → `POST /hindcast` now requires a `HindcastRequest`
  JSON body (was previously a no-argument stub returning dict). New
  `POST /forward` endpoint added. Affected: Sayan (frontend must send
  Slick in hindcast request), Nimit (will send ForwardSimulationRequest
  after attribution).
- **Scientific decisions:**
  - KDE projection centered on **particle mean** (not ground truth).
  - `probability` field = KDE density mass fraction, NOT calibrated probability.
  - `predicted_footprint` = convex hull particle envelope, NOT observed footprint.
  - matplotlib required for headless contour extraction (no GUI).
- **Next:**
  - **Nimit:** receives `HindcastResponse.source_region` (geometry + centroid +
    time window + probability), `backward_trajectory`, and
    `trajectory_timestamps_utc`. Filters AIS vessels within the source region's
    spatial geometry and `[start_time_utc, end_time_utc]` temporal window.
    After attribution, sends `ForwardSimulationRequest` to `POST /forward`
    with `{incident_id, vessel_mmsi, release_location, release_time_utc,
    observation_time_utc}`.
  - **Sayan:** receives all data as GeoJSON/JSON — no xarray/NetCDF knowledge
    needed. Must distinguish: observed slick vs. backward reconstruction vs.
    source region vs. forward predicted envelope.
  - **Configuration:** production deployment must provide real forcing NetCDF
    files via `DRIFT_FORCING_CURRENTS_PATH` and `DRIFT_FORCING_WIND_PATH`.

### 2026-08-30 17:10 IST · Claude (for Satyam) · branch context-brain
- **What:** created `CONTEXT_BRAIN.md` + this `HANDOFF_LOG.md`; seeded the
  log with the project's history to date.
- **Why:** give every future agent/human a zero-context-loss starting point
  and an enforced change journal (same pattern that carried the ML module
  across machines).
- **Verified:** docs only — no code touched; test suite untouched (green at
  100/100 on `feature/ml-integration`).
- **BREAKING:** no
- **Next:** Parth merges `feature/ml-integration` and this branch; Ved
  starts `run_hindcast` against the real Slick input (see brain §5).

### 2026-08-30 16:45 IST · Claude (for Satyam) · branch feature/ml-integration
- **What:** implemented `app/services/detection.py` (async httpx proxy to
  the deployed ML service + pure `features_to_slicks` adapter +
  `ml_service_health`); rewrote `app/api/v1/endpoints/detection.py`
  (`response_model=list[Slick]`, optional `acquired_at_utc` Form field,
  `GET /health/ml`); added `ML_SERVICE_URL`/`ML_SERVICE_TIMEOUT` to
  `app/core/config.py` + `.env.example`; added
  `tests/test_detection_service.py` (5 contract tests); updated
  `tests/test_endpoints.py` for the list response.
- **Why:** connect the backend to Satyam's live detection service.
- **Verified:** full suite 100/100; live E2E through
  `POST /api/v1/detect` with the demo scene → 1 Slick, 266.928 km²,
  conf 0.768, MultiPolygon, supplied timestamp preserved (37.6 s).
- **BREAKING:** yes → `/detect` response is now `list[Slick]` (was a
  single `Slick`) and the service function is async. Affected: Parth
  (review), Sayan (frontend parses a list), Ved (hindcast consumes
  `slicks[i]`). Rationale: scenes routinely contain several slicks;
  `[]` = clean water.
- **Next:** Parth reviews/merges; frontend + hindcast consume the list.

### 2026-08-30 15:55 IST · Claude (for Satyam) · branch main
- **What:** pushed `docs/OilTrace_Detection_API.md` (+ HTML twin) — the ML
  service API reference with a 4-point adapter guide against
  `app/models/slick.py`.
- **Why:** Ved and Parth needed the endpoint contract; reading the backend
  models surfaced 4 integration gaps worth documenting (single-vs-list
  response, missing sensing time, `image` vs `file` field name,
  MultiPolygon).
- **Verified:** doc cross-checked against the live service responses and
  the Pydantic models at commit `686e766`.
- **BREAKING:** no
- **Next:** implement the integration (done — see entry above).

### 2026-08-30 (earlier) · Satyam's ML lane (separate repo) · context
- **What:** ML service deployed at
  `https://vscimatic999--oiltrace-detection-web.modal.run` (Modal free
  tier) after HF Spaces paywalled Docker in July 2026. Final model
  `E5_focal`: val Dice 0.350 / object precision 0.471 / recall(≥10 ha)
  0.667; postprocessing frozen from validation sweeps (t=0.325, 250 px,
  conf 0.60). Part III test set sealed.
- **Why:** context for anyone touching `/detect` — full story in
  `Satyam087/CodeRabbit` git history and its context-brain pair.
- **Verified:** live round trip 24 MB scene → 18 s server-side inference.
- **BREAKING:** n/a
- **Next:** tracked in the ML repo (29-scene backfill, curriculum training,
  one-shot Part III evaluation before final submission).

### pre-2026-08-30 · Parth · branch main
- **What:** repo initialized: FastAPI modular monolith, five-stage endpoint
  skeleton, strict Pydantic v2 contracts (geometry union, UTC validation,
  Slick/SourceRegion/Vessel/Attribution/Replay/SatelliteScene), 95 tests,
  `Complete_Flow.md`, per-object docx docs.
- **Why:** contract-first foundation for the OilTrace MVP.
- **Verified:** pytest suite green.
- **BREAKING:** n/a (baseline)
- **Next:** wire real services into the stubs (detection done; hindcast,
  vessels, attribution, replay open).
