# ML-service — OilTrace SAR Detection

| Folder | Contents |
|---|---|
| `service/` | Deployable detection API (FastAPI + Docker): Sentinel-1 VV+VH → U-Net → GeoJSON slick polygons. Live on Modal: https://vscimatic999--oiltrace-detection-web.modal.run |
| `ml/` | Training & evaluation code (U-Net, loaders, metrics, threshold/TTA sweeps) |
| `manifests/` | Dataset manifests (Zenodo oil-spill dataset, 450 pixel-verified scenes) |
| `runs/` | Experiment records (manifests + metric histories; weight binaries excluded — the deployed E5_focal checkpoint is baked into the Modal image) |
| `docs/` | API reference + judge card |
