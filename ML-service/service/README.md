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

Model: U-Net (VV+VH, 512² tiled inference), threshold selected on held-out
validation including look-alike hard negatives. Imagery credit:
Trujillo-Acatitla et al., Zenodo (CC-BY 4.0).
