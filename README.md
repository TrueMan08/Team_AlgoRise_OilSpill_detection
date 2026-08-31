# OilSpill-detect — OilTrace (SIH 2026 · SIH26143)

Satellite oil-spill detection + AIS vessel attribution system.

| Folder | Contents |
|---|---|
| `backend/` | FastAPI backend — OpenDrift hindcast/forward simulation, AIS vessel query, attribution engine, counterfactual validation, replay. Deployed on Modal. |
| `ML-service/` | SAR detection — U-Net service (Sentinel-1 VV+VH → GeoJSON slicks), training/eval code, dataset manifests, experiment records. Deployed on Modal. |
| `demo-frontend/` | React + Leaflet investigation dashboard — 6-stage workflow (detection → hindcast → vessels → attribution → forward → counterfactual), OpenDrift-style drift particle animation, Norway demo scenario. |

Team AlgoRise.
