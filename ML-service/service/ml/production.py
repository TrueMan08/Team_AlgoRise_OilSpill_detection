"""Validation-selected X1c + C3 + V1 component-verifier inference pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from ml.gate_eval import comps, load_classifier
from ml.inference import load_model
from ml.patch_dataset import N1_CENTER, N1_SCALE
from ml.verifier import comp_features

TILE = 512
SEGMENTATION_THRESHOLD = 0.8
MIN_AREA_PX = 250
VERIFIER_THRESHOLD = 0.5


def load_verified_pipeline(model_dir: Path, device: torch.device):
    """Load the trained networks and train-fitted verifier parameters."""
    seg_path = model_dir / "x1c_r34_strict.pth"
    clf_path = model_dir / "c3_scene_r34.pth"
    verifier_path = model_dir / "v1_verifier.json"
    seg, seg_meta = load_model(seg_path, device, use_pretrained=False)
    clf, clf_meta = load_classifier(str(clf_path), device, pretrained=False)
    verifier = json.loads(verifier_path.read_text(encoding="utf-8"))
    return seg, seg_meta, clf, clf_meta, verifier


def predict_verified_scene(seg, clf, clf_meta: dict, verifier: dict,
                           image: np.ndarray, device: torch.device,
                           batch_size: int = 4):
    """Run the calibrated component pipeline over non-overlapping 512 px tiles.

    Each tile gets its own component-level verifier score, matching the scale
    used to fit V1. Accepted masks are mosaicked before geospatial polygon
    extraction so touching detections across tile edges can join.
    """
    _, height, width = image.shape
    padded_h = ((height + TILE - 1) // TILE) * TILE
    padded_w = ((width + TILE - 1) // TILE) * TILE
    padded = np.pad(image, ((0, 0), (0, padded_h - height),
                            (0, padded_w - width)), mode="edge")
    norm = (padded - N1_CENTER) / N1_SCALE
    coords = [(y, x) for y in range(0, padded_h, TILE)
              for x in range(0, padded_w, TILE)]
    mosaic_prob = np.zeros((height, width), dtype=np.float32)
    accepted = np.zeros((height, width), dtype=np.uint8)

    mu = np.asarray(verifier["mu"], dtype=np.float64)
    sd = np.asarray(verifier["sd"], dtype=np.float64)
    weights = np.asarray(verifier["w"], dtype=np.float64)
    bias = float(verifier["b"])
    lk_idx = clf_meta["classes"].index("Lookalike")

    with torch.no_grad():
        for start in range(0, len(coords), batch_size):
            chunk = coords[start:start + batch_size]
            xb = torch.from_numpy(np.stack(
                [norm[:, y:y + TILE, x:x + TILE] for y, x in chunk]
            ).astype(np.float32)).to(device)
            with torch.amp.autocast(device.type, enabled=device.type == "cuda"):
                logits = seg(xb).float()
                cls_logits = clf(xb).float()
            probs = torch.sigmoid(logits)[:, 0].cpu().numpy()
            p_lookalike = torch.softmax(cls_logits, 1)[:, lk_idx].cpu().numpy()

            for (y, x), prob, p_lk, tensor in zip(chunk, probs, p_lookalike, xb):
                binary = (prob > SEGMENTATION_THRESHOLD).astype(np.uint8)
                candidates = [c for c in comps(binary) if c["px"] >= MIN_AREA_PX]
                if not candidates:
                    continue
                raw_vv = tensor[0].cpu().numpy() * N1_SCALE + N1_CENTER
                features = np.asarray([
                    comp_features(c, prob, raw_vv, len(candidates),
                                  float(binary.mean()), float(p_lk))
                    for c in candidates
                ], dtype=np.float64)
                scores = 1.0 / (1.0 + np.exp(-(((features - mu) / sd) @ weights + bias)))
                valid_h, valid_w = min(TILE, height - y), min(TILE, width - x)
                mosaic_prob[y:y + valid_h, x:x + valid_w] = prob[:valid_h, :valid_w]
                tile_mask = np.zeros((TILE, TILE), dtype=np.uint8)
                for component, score in zip(candidates, scores):
                    if score >= VERIFIER_THRESHOLD:
                        tile_mask[component["mask"]] = 1
                accepted[y:y + valid_h, x:x + valid_w] = tile_mask[:valid_h, :valid_w]
    return mosaic_prob, accepted
