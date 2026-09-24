---
title: OilTrace Detection Service
emoji: 🛢️
colorFrom: gray
colorTo: yellow
sdk: docker
pinned: false
---

# OilTrace SAR+ML Detection Service (SIH26143 · Team AlgoRise)

Sentinel-1 VV+VH GeoTIFF in → oil-slick detection GeoJSON out.

- `GET /detect/demo` — instant cached detection for the bundled demo scene
- `POST /detect` — multipart `file` = 2-band georeferenced GeoTIFF → GeoJSON
  FeatureCollection (polygon, centroid, `area_km2`, `confidence` per slick)
- `GET /demo/scene` — the demo GeoTIFF for round-trip testing
- `GET /health`

Model: X1c ResNet-34 U-Net segmentation → C3 ResNet-34 look-alike context →
V1 trained component verifier. Inference uses VV+VH, 512² tiles, segmentation
threshold 0.8, 250 px minimum component area, and verifier score threshold
0.5. The operating point was selected on held-out validation only; the sealed
Part III test set has not been evaluated. Checkpoint files are stored with
Git LFS under `data/models/`. Imagery credit: Trujillo-Acatitla et al.,
Zenodo (CC-BY 4.0).

The verifier was fitted on training patches and evaluated on the held-out
validation set. The scene-level validation metrics are object precision
0.817 and recall 0.812 for slicks ≥10 ha at score ≥0.5. These are research
validation results, not a production guarantee.
