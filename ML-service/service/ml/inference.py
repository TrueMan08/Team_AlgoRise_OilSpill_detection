"""OilTrace — full-scene inference + geometry: SAR TIFF → oil GeoJSON.

The deployed detection path (dev step 9, adapted for the prototype):
  georeferenced VV+VH scene
    → overlapped 512² tiled inference (stitched by averaging probabilities)
    → threshold → min-area filter → contours → Shapely polygons
    → pixel-centre geotransform → WGS84 → UTM-projected km² areas
    → GeoJSON FeatureCollection matching Parth's detection contract.

Geometry mirrors the pipeline validated on real data in technical_checks.py
(analysis/slick_sample.geojson). Threshold and min-area are CANDIDATES
(spec: final values come from the validation sweep) — both recorded in the
output properties so nothing masquerades as tuned.

Run:
  .venv/Scripts/python.exe -m ml.inference --scene <path.tif> \
      --checkpoint runs/E0_partial/best.pth --out analysis/demo_detection.geojson
"""
from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

import cv2
import numpy as np
import pyproj
import rasterio
import torch
from rasterio.errors import NotGeoreferencedWarning
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shp_transform

from ml.model import UNet
from ml.patch_dataset import N1_CENTER, N1_SCALE

warnings.simplefilter("ignore", NotGeoreferencedWarning)

TILE = 512
STRIDE = 384          # 128 px overlap — CANDIDATE (spec: overlap % is EXPERIMENT)
THRESHOLD = 0.325     # SELECTED on validation for E5_focal: dice 0.348 vs 0.350 max, but scene-level slick coherence strongly favors 0.325 (0.475 fragments large slicks)
MIN_AREA_PX = 250     # SELECTED on validation (analysis/object_eval.json): 5x object precision, large-slick recall unchanged
MIN_CONFIDENCE = 0.60  # SELECTED on validation for E5_focal (analysis/confidence_sweep.json): obj precision 0.471, recall(>=10ha) 0.667; demo scenes confirm traps cleaned, all main slicks retained


def load_model(checkpoint: Path, dev: torch.device) -> tuple[UNet, dict]:
    ckpt = torch.load(checkpoint, map_location=dev, weights_only=False)
    norm = (ckpt.get("config") or {}).get("norm_layer", "batch")
    model = UNet(norm=norm).to(dev)
    model.load_state_dict(ckpt["model"])
    model.eval()
    return model, {"epoch": ckpt.get("epoch"), "val": ckpt.get("val"),
                   "config": ckpt.get("config")}


def predict_scene(model: UNet, img: np.ndarray, dev: torch.device,
                  batch: int = 4) -> np.ndarray:
    """img (2,H,W) raw dB float32 -> stitched probability map (H,W)."""
    _, h, w = img.shape
    x = (img - N1_CENTER) / N1_SCALE  # must match training normalization (N1)
    ys = sorted({min(y, h - TILE) for y in range(0, h, STRIDE)})
    xs = sorted({min(xx, w - TILE) for xx in range(0, w, STRIDE)})
    prob = np.zeros((h, w), dtype=np.float32)
    weight = np.zeros((h, w), dtype=np.float32)
    tiles = [(y, xx) for y in ys for xx in xs]
    with torch.no_grad():
        for i0 in range(0, len(tiles), batch):
            chunk = tiles[i0:i0 + batch]
            xb = torch.from_numpy(np.stack(
                [x[:, y:y + TILE, xx:xx + TILE] for y, xx in chunk])).to(dev)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                logits = model(xb)
            pb = torch.sigmoid(logits.float()).cpu().numpy()[:, 0]
            for (y, xx), p in zip(chunk, pb):
                prob[y:y + TILE, xx:xx + TILE] += p
                weight[y:y + TILE, xx:xx + TILE] += 1
    return prob / np.maximum(weight, 1)


def mask_to_features(mask: np.ndarray, prob: np.ndarray, transform,
                     bounds, scene_id: str) -> list[dict]:
    px_deg = abs(transform.a)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    feats = []
    for k, c in enumerate(sorted(contours, key=cv2.contourArea, reverse=True)):
        if cv2.contourArea(c) < MIN_AREA_PX or len(c) < 3:
            continue
        px = c.squeeze(1).astype(float)
        geo = [transform * (xx + 0.5, y + 0.5) for xx, y in px]  # pixel-centre
        poly = Polygon(geo).buffer(0).simplify(px_deg * 2)
        if poly.is_empty or not poly.is_valid:
            continue
        # confidence: mean predicted probability inside the component
        comp = np.zeros_like(mask, dtype=np.uint8)
        cv2.drawContours(comp, [c], -1, 1, thickness=-1)
        # mean prob over the component's ACTUAL pixels (filled contour would
        # dilute a ragged slick's confidence with its low-prob holes)
        comp_px = comp.astype(bool) & mask.astype(bool)
        conf = float(prob[comp_px].mean()) if comp_px.any() else 0.0
        if conf < MIN_CONFIDENCE:
            continue
        lon_c, lat_c = poly.centroid.x, poly.centroid.y
        utm = pyproj.CRS(f"+proj=utm +zone={int((lon_c + 180) // 6) + 1} "
                         f"+datum=WGS84 +units=m")
        to_utm = pyproj.Transformer.from_crs("EPSG:4326", utm,
                                             always_xy=True).transform
        area_km2 = shp_transform(to_utm, poly).area / 1e6
        inside = (bounds.left <= lon_c <= bounds.right
                  and bounds.bottom <= lat_c <= bounds.top)
        feats.append({
            "type": "Feature",
            "properties": {
                "id": f"slick_{k:03d}",
                "scene_id": scene_id,
                "confidence": round(conf, 4),
                "area_km2": round(area_km2, 3),
                "centroid": {"lat": round(lat_c, 5), "lon": round(lon_c, 5)},
                "centroid_inside_scene": inside,
            },
            "geometry": mapping(poly),
        })
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True)
    ap.add_argument("--checkpoint", default="runs/E0_partial/best.pth")
    ap.add_argument("--out", default="analysis/demo_detection.geojson")
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    args = ap.parse_args()

    t0 = time.time()
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, meta = load_model(Path(args.checkpoint), dev)
    print(f"checkpoint: epoch {meta['epoch']}, val {meta['val']}")

    with rasterio.open(args.scene) as src:
        assert src.count == 2 and src.crs is not None, "need georeferenced VV+VH scene"
        img = src.read().astype(np.float32)
        transform, bounds = src.transform, src.bounds
    scene_id = Path(args.scene).stem
    print(f"scene {scene_id}: {img.shape[1]}x{img.shape[2]}, "
          f"inference on {dev} ...")

    prob = predict_scene(model, img, dev)
    mask = (prob > args.threshold).astype(np.uint8)
    print(f"oil pixels above threshold {args.threshold}: {int(mask.sum()):,} "
          f"({mask.mean()*100:.2f}% of scene)")

    feats = mask_to_features(mask, prob, transform, bounds, scene_id)
    out = {
        "type": "FeatureCollection",
        "properties": {
            "scene_id": scene_id,
            "model": {"name": "OilTrace-U-Net", "experiment":
                      meta["config"].get("experiment") if meta["config"] else "?",
                      "checkpoint_epoch": meta["epoch"]},
            "postprocessing": {"threshold": args.threshold,
                               "min_area_px": MIN_AREA_PX,
                               "min_confidence": MIN_CONFIDENCE,
                               "tile": TILE, "stride": STRIDE,
                               "selected_on": "validation only"},
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "features": feats,
    }
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(f"{len(feats)} detection polygon(s) -> {args.out} "
          f"({time.time()-t0:.0f}s total)")


if __name__ == "__main__":
    main()
