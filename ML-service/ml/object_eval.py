"""OilTrace — object-level evaluation + min-area sweep + error buckets
(frozen spec §07-08: min-area from {0,25,50,100,250} on validation only;
object metrics via max-IoU matching; component P/R; centroid error).

One pass over the val set at the validation-selected threshold:
- per patch: GT components and predicted components (8-connectivity)
- greedy max-IoU matching (a GT component counts as DETECTED if its best
  unmatched prediction reaches IoU >= MATCH_IOU)
- the min-area filter is swept over predicted components
- every FP component is attributed to its patch's scene category
  (Oil / Lookalike / No oil) -> the error buckets

Writes analysis/object_eval.json.
Run:  .venv/Scripts/python.exe -m ml.object_eval [checkpoint]
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch

from ml.inference import load_model
from ml.patch_dataset import PatchDataset

THRESHOLD = 0.325
MIN_AREAS = [0, 25, 50, 100, 250]
MATCH_IOU = 0.1          # generous: "found the object at all"; also report 0.3
PX_METERS = 10.0         # ~10 m pixels (measured ~8.98e-5 deg)


def components(mask: np.ndarray):
    n, lab, stats, cents = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8)
    out = []
    for k in range(1, n):
        out.append({"px": int(stats[k, cv2.CC_STAT_AREA]),
                    "centroid": (float(cents[k][0]), float(cents[k][1])),
                    "mask": lab == k})
    return out


def main():
    ckpt = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/E0_finetune/best.pth")
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, meta = load_model(ckpt, dev)
    ds = PatchDataset(split="val", normalization="N1")

    gt_total = 0
    gt_records = {a: [] for a in MIN_AREAS}   # (gt_px, detected, strict)
    gt_detected = {a: 0 for a in MIN_AREAS}
    gt_detected_strict = {a: 0 for a in MIN_AREAS}   # IoU >= 0.3
    pred_total = {a: 0 for a in MIN_AREAS}
    pred_matched = {a: 0 for a in MIN_AREAS}
    fp_by_cat = {a: defaultdict(int) for a in MIN_AREAS}      # FP components
    fp_px_by_cat = {a: defaultdict(int) for a in MIN_AREAS}   # FP pixels
    centroid_err_m = {a: [] for a in MIN_AREAS}
    missed_gt_sizes = []
    t0 = time.time()

    with torch.no_grad():
        for i0 in range(0, len(ds), 16):
            xs, ms, cats = [], [], []
            for i in range(i0, min(i0 + 16, len(ds))):
                img, mask, scene = ds[i]
                xs.append(img)
                ms.append(mask[0].numpy().astype(np.uint8))
                cats.append(str(scene).split("/")[0])
            x = torch.stack(xs).to(dev)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                p = torch.sigmoid(model(x).float())
            preds = (p[:, 0].cpu().numpy() > THRESHOLD).astype(np.uint8)

            for pred, gt, cat in zip(preds, ms, cats):
                gcomps = components(gt) if gt.any() else []
                pcomps = components(pred) if pred.any() else []
                gt_total += len(gcomps)
                for a in MIN_AREAS:
                    kept = [c for c in pcomps if c["px"] >= a]
                    pred_total[a] += len(kept)
                    used = [False] * len(kept)
                    for g in gcomps:
                        best_iou, best_j = 0.0, -1
                        for j, c in enumerate(kept):
                            if used[j]:
                                continue
                            inter = np.logical_and(g["mask"], c["mask"]).sum()
                            if inter == 0:
                                continue
                            iou = inter / (g["px"] + c["px"] - inter)
                            if iou > best_iou:
                                best_iou, best_j = iou, j
                        det = best_iou >= MATCH_IOU
                        gt_records[a].append((g["px"], det, best_iou >= 0.3))
                        if det:
                            used[best_j] = True
                            gt_detected[a] += 1
                            pred_matched[a] += 1
                            if best_iou >= 0.3:
                                gt_detected_strict[a] += 1
                            c = kept[best_j]
                            d = np.hypot(c["centroid"][0] - g["centroid"][0],
                                         c["centroid"][1] - g["centroid"][1])
                            centroid_err_m[a].append(d * PX_METERS)
                        elif a == MIN_AREAS[0]:
                            missed_gt_sizes.append(g["px"])
                    for j, c in enumerate(kept):
                        if not used[j]:
                            fp_by_cat[a][cat] += 1
                            fp_px_by_cat[a][cat] += c["px"]

    rows = []
    for a in MIN_AREAS:
        ce = np.array(centroid_err_m[a]) if centroid_err_m[a] else np.array([0.0])
        by_floor = {}
        for floor in (0, 25, 50, 250, 1000):
            rel = [(px, det) for px, det, _ in gt_records[a] if px >= floor]
            by_floor[str(floor)] = {
                "gt_n": len(rel),
                "recall": round(sum(d for _, d in rel) / max(len(rel), 1), 4)}
        rows.append({
            "min_area_px": a,
            "gt_recall_by_size_floor": by_floor,
            "object_recall": round(gt_detected[a] / max(gt_total, 1), 4),
            "object_recall_iou30": round(gt_detected_strict[a] / max(gt_total, 1), 4),
            "object_precision": round(pred_matched[a] / max(pred_total[a], 1), 4),
            "pred_components": pred_total[a],
            "fp_components_by_category": dict(fp_by_cat[a]),
            "fp_pixels_by_category": dict(fp_px_by_cat[a]),
            "centroid_error_m": {"median": round(float(np.median(ce)), 1),
                                 "p90": round(float(np.percentile(ce, 90)), 1)},
        })
        print(f"min_area {a:4d}: obj recall {rows[-1]['object_recall']:.3f} "
              f"(iou>=0.3: {rows[-1]['object_recall_iou30']:.3f}) "
              f"precision {rows[-1]['object_precision']:.3f} "
              f"preds {pred_total[a]} centroid median {rows[-1]['centroid_error_m']['median']}m")

    missed = np.array(missed_gt_sizes) if missed_gt_sizes else np.array([0])
    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checkpoint": str(ckpt), "threshold": THRESHOLD,
        "match_iou": MATCH_IOU, "gt_components": gt_total,
        "sweep": rows,
        "missed_gt_component_sizes_px": {
            "n": int(len(missed_gt_sizes)),
            "median": float(np.median(missed)),
            "p90": float(np.percentile(missed, 90))},
        "note": "validation only; patch-level components (border-clipped); "
                "centroid error in metres assuming 10 m pixels",
        "secs": round(time.time() - t0),
    }
    Path("analysis/object_eval.json").write_text(json.dumps(out, indent=1))
    print(f"wrote analysis/object_eval.json ({out['secs']}s)")


if __name__ == "__main__":
    main()
