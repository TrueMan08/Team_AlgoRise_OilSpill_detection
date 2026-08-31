"""OilTrace SAR+ML detection service — the Satyam module of the OilTrace MVP.

POST a georeferenced Sentinel-1 VV+VH GeoTIFF, get back oil-slick detections
as a GeoJSON FeatureCollection (polygon, centroid, area_km2, confidence per
slick) — the contract the hindcasting module consumes.

Endpoints:
  GET  /            service + model info
  GET  /health      liveness for orchestration
  GET  /detect/demo instant cached result for the bundled demo scene
  GET  /demo/scene  download the bundled demo GeoTIFF (for round-trip tests)
  POST /detect      multipart 'file' = GeoTIFF -> live inference -> GeoJSON
                    (optional ?threshold=, default = validation-selected)

Model: OilTrace U-Net (experiment from checkpoint config) — VV+VH 512-tile inference, threshold
0.325 selected on validation only; Part III test set untouched.
"""
from __future__ import annotations

import io
import json
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
import torch
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ml.inference import load_model, mask_to_features, predict_scene

ROOT = Path(__file__).resolve().parent
CHECKPOINT = ROOT / "data" / "oiltrace_unet.pth"
DEMO_SCENE = ROOT / "data" / "demo_scene_00067.tif"
DEMO_RESULT = ROOT / "data" / "demo_detection_00067.geojson"
DEFAULT_THRESHOLD = 0.325   # selected on validation (analysis/threshold_sweep.json)
MAX_UPLOAD_MB = 80

app = FastAPI(title="OilTrace SAR+ML Detection Service", version="0.1.0")

torch.set_num_threads(max(1, (torch.get_num_threads() or 2)))
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL, META = load_model(CHECKPOINT, DEV)   # loaded ONCE at startup


def _model_info() -> dict:
    return {
        "name": "OilTrace-U-Net",
        "experiment": (META.get("config") or {}).get("experiment", "?"),
        "checkpoint_epoch": META.get("epoch"),
        "validation": META.get("val"),
        "default_threshold": DEFAULT_THRESHOLD,
        "validation_note": "metrics on scene-level held-out validation "
                           "including look-alike hard negatives; Part III "
                           "test set sealed and untouched",
        "device": str(DEV),
    }


@app.get("/")
def root():
    return {
        "service": "OilTrace SAR+ML detection",
        "team": "AlgoRise · SIH26143",
        "model": _model_info(),
        "endpoints": {
            "GET /health": "liveness",
            "GET /detect/demo": "cached demo detection (instant)",
            "GET /demo/scene": "download demo GeoTIFF",
            "POST /detect": "multipart 'file' GeoTIFF -> detection GeoJSON",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": True, "device": str(DEV)}


@app.get("/detect/demo")
def detect_demo():
    return JSONResponse(json.loads(DEMO_RESULT.read_text()))


@app.get("/demo/scene")
def demo_scene():
    return FileResponse(DEMO_SCENE, media_type="image/tiff",
                        filename=DEMO_SCENE.name)


@app.post("/detect")
async def detect(file: UploadFile = File(...),
                 threshold: float = Query(DEFAULT_THRESHOLD, ge=0.05, le=0.95)):
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_MB * 1e6:
        raise HTTPException(413, f"upload exceeds {MAX_UPLOAD_MB} MB")
    t0 = time.time()
    # rasterio needs a real file for some TIFF layouts; use a temp file
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        try:
            with rasterio.open(tmp_path) as src:
                if src.count != 2:
                    raise HTTPException(
                        422, f"expected 2 bands (VV,VH), got {src.count}")
                if src.crs is None or src.transform.is_identity:
                    raise HTTPException(422, "scene is not georeferenced")
                img = src.read().astype(np.float32)
                transform, bounds = src.transform, src.bounds
        except rasterio.errors.RasterioIOError as e:
            raise HTTPException(422, f"not a readable GeoTIFF: {e}")
        prob = predict_scene(MODEL, img, DEV)
        mask = (prob > threshold).astype(np.uint8)
        feats = mask_to_features(mask, prob, transform, bounds,
                                 Path(file.filename or "scene").stem)
    finally:
        tmp_path.unlink(missing_ok=True)
    return JSONResponse({
        "type": "FeatureCollection",
        "properties": {
            "scene_id": Path(file.filename or "scene").stem,
            "model": _model_info(),
            "threshold": threshold,
            "inference_seconds": round(time.time() - t0, 1),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "features": feats,
    })
