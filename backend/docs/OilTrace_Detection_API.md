# OilTrace Detection Service — API Reference

Satyam's SAR+ML module, **live** and callable now:

```
BASE = https://vscimatic999--oiltrace-detection-web.modal.run
```

Sentinel-1 VV+VH GeoTIFF in → oil-slick detections as GeoJSON out.
No authentication. All coordinates WGS84. Hosted on Modal free tier
(scales to zero — see cold-start note).

Model: `E5_focal` U-Net (val Dice 0.350, object precision 0.47 on validation
*including* look-alike hard negatives). Postprocessing frozen from
validation sweeps: threshold 0.325, min slick 250 px (~0.025 km²),
min confidence 0.60. Part III test set sealed/untouched.

---

## Before integrating — three things to know

1. **Cold start.** The service sleeps after ~5 idle minutes; the next request
   pays **+20–40 s** wake-up. Set client timeouts **≥ 120 s** (300 s for
   `/detect`), and hit `GET /health` a minute before any live demo.
2. **Live inference takes ~20–60 s** per 2048² scene (CPU). Treat
   `POST /detect` as a long call / async job, never UI-blocking.
   `GET /detect/demo` is instant (pre-computed).
3. **GeoJSON axis order is `[longitude, latitude]`** in all geometry
   coordinates (RFC 7946). The `centroid` property is a named
   `{lat, lon}` object.

---

## Endpoints

### `GET /health` — liveness / warm-up

```json
{"status": "ok", "model_loaded": true, "device": "cpu"}
```

### `GET /` — service + model info

Model experiment name, checkpoint epoch, full validation metrics, default
threshold, endpoint list. Log `model.experiment` for provenance.

### `GET /detect/demo` — instant cached result (start here)

Pre-computed detection for the bundled demo scene (a real 267 km² slick,
Eastern Mediterranean). **Identical schema to a live `POST /detect`
response** — build and test integration against this first.

### `GET /demo/scene` — the demo GeoTIFF (24 MB)

For round-trip testing `POST /detect`.

### `POST /detect` — the main endpoint

| Part | Requirement |
|---|---|
| `file` (multipart form field — **note the field name**) | GeoTIFF, exactly **2 bands** (1=VV, 2=VH), Sigma0 dB, **georeferenced** (CRS + transform). Max **80 MB**. |
| `threshold` (query, optional) | 0.05–0.95. **Omit it** — default 0.325 is validation-selected. |

```bash
curl -m 300 -F "file=@scene.tif" $BASE/detect -o result.geojson
```

```python
import requests
with open("scene.tif", "rb") as f:
    r = requests.post(f"{BASE}/detect", files={"file": f}, timeout=300)
detections = r.json()
```

#### Response — GeoJSON FeatureCollection

```jsonc
{
  "type": "FeatureCollection",
  "properties": {
    "scene_id": "scene",                  // from uploaded filename
    "model": { "name": "OilTrace-U-Net", "experiment": "E5_focal",
               "checkpoint_epoch": 5, "validation": { /* ... */ } },
    "threshold": 0.325,
    "inference_seconds": 18.0,
    "generated": "2026-08-30T09:51:04Z"   // PROCESSING time (UTC), not sensing time
  },
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "slick_000",                // largest first
        "scene_id": "scene",
        "confidence": 0.768,              // 0.60–1.0, uncalibrated model score
        "area_km2": 266.928,              // UTM-projected (metres), never degrees
        "centroid": { "lat": 35.63533, "lon": 34.8704 },
        "centroid_inside_scene": true
      },
      "geometry": { "type": "Polygon",    // or MultiPolygon
                    "coordinates": [[[lon, lat], "..."]] }
    }
  ]
}
```

- `features: []` (empty) = **no oil detected** — a valid, common result.
- `confidence` is a model score, not a calibrated probability. ≥0.75 is a
  solid detection; 0.60–0.70 deserves an "uncertain" tag in the UI.
- Centroid accuracy on validation: **median ~85 m** from truth.

#### Errors

| Status | Cause | `detail` |
|---|---|---|
| 413 | upload > 80 MB | `upload exceeds 80 MB` |
| 422 | unreadable file | `not a readable GeoTIFF: …` |
| 422 | wrong bands | `expected 2 bands (VV,VH), got N` |
| 422 | no CRS/transform | `scene is not georeferenced` |
| timeout | cold start + upload exceeded client timeout | retry once, timeout ≥300 s |

---

## Mapping to this backend's `Slick` contract — 4 adapter notes

Read against `app/models/slick.py` as of commit `686e766`:

1. **One scene can contain MANY slicks.** The detection service returns a
   FeatureCollection with N features (largest first); the backend `/detect`
   currently declares `response_model=Slick` (singular). Either change it to
   `list[Slick]`, or have the adapter take `features[0]` (the largest) and
   log the rest — but multi-slick scenes are real (median 25 GT components
   per oil scene in the dataset).
2. **`timestamp_utc` cannot come from the detection service.** The dataset's
   TIFFs carry no acquisition time, so the service's `generated` field is
   *processing* time. The orchestration layer must supply the scene's
   observation time from scene metadata and inject it into `Slick`. For the
   cached demo bundle, agree one fixed timestamp.
3. **Field names line up almost everywhere:**
   `properties.id → Slick.id`, `properties.area_km2 → area_km2`,
   `properties.confidence → confidence` (already 0–1 ✓),
   `properties.centroid {lat,lon} → models.geometry.Point` ✓ (same shape),
   `geometry → GeoJSONGeometry` (ensure `MultiPolygon` is accepted —
   the service emits it for slicks whose repaired outline splits),
   `properties.scene_id → scene_id`, and set `sensor = "Sentinel-1"`.
4. **The backend endpoint's upload field is `image`; the service expects
   `file`.** The proxy/service layer must forward the upload under the
   name `file`.

---

## Integration checklists

**Ved (hindcast):** build against `GET /detect/demo` first · seed backward
drift from `centroid` (optionally scatter particles across `geometry`) ·
handle empty `features` and `MultiPolygon` · attach observation time
yourself (note 2 above).

**Parth (backend):** proxy `/detect` as an async job (timeout ≥300 s, one
retry) · warm with `GET /health` on app start and pre-demo · cache
`/detect/demo`'s response in Supabase for the judged demo per the
cached-bundle plan · log `properties.model` for provenance.

---

*OilTrace detection API v0.1.0 · model E5-focal · SAR data credit:
Trujillo-Acatitla et al., Zenodo, CC-BY 4.0 · 30 Aug 2026 ·
service source: `Satyam087/CodeRabbit` → `service/`*
