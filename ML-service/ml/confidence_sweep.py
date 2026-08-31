"""OilTrace — per-component confidence filter sweep (validation only).

Gallery observation: real-slick components carry mean probability 0.8+,
hard-trap components ~0.5. This sweeps a minimum mean-probability cutoff
applied ON TOP of the frozen threshold 0.325 + min-area 250, measuring
object-level precision/recall (max-IoU >= 0.1) and >=1000px recall.

Run:  .venv/Scripts/python.exe -m ml.confidence_sweep
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch

from ml.inference import load_model
from ml.patch_dataset import PatchDataset

import sys as _sys
THRESHOLD = float(_sys.argv[2]) if len(_sys.argv) > 2 else 0.325
CKPT = _sys.argv[1] if len(_sys.argv) > 1 else "runs/E0_finetune/best.pth"
MIN_AREA = 250
CONF_CUTS = [0.0, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]


def comps(mask):
    n, lab, stats, cents = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8)
    return [{"px": int(stats[k, cv2.CC_STAT_AREA]), "mask": lab == k}
            for k in range(1, n)]


def main():
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, _ = load_model(Path(CKPT), dev)
    ds = PatchDataset(split="val", normalization="N1")

    stats = {c: {"pred": 0, "matched": 0, "fp_px_cat": defaultdict(int),
                 "gt_det": 0, "gt_det_big": 0} for c in CONF_CUTS}
    gt_n = 0
    gt_big_n = 0
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
            probs = p[:, 0].cpu().numpy()
            for prob, gt, cat in zip(probs, ms, cats):
                pred = (prob > THRESHOLD).astype(np.uint8)
                pcomps = [c for c in comps(pred) if c["px"] >= MIN_AREA] \
                    if pred.any() else []
                for c in pcomps:
                    c["conf"] = float(prob[c["mask"]].mean())
                gcomps = comps(gt) if gt.any() else []
                gt_n += len(gcomps)
                gt_big_n += sum(1 for g in gcomps if g["px"] >= 1000)
                for cut in CONF_CUTS:
                    kept = [c for c in pcomps if c["conf"] >= cut]
                    st = stats[cut]
                    st["pred"] += len(kept)
                    used = [False] * len(kept)
                    for g in gcomps:
                        best, bj = 0.0, -1
                        for j, c in enumerate(kept):
                            if used[j]:
                                continue
                            inter = np.logical_and(g["mask"], c["mask"]).sum()
                            if inter:
                                iou = inter / (g["px"] + c["px"] - inter)
                                if iou > best:
                                    best, bj = iou, j
                        if best >= 0.1:
                            used[bj] = True
                            st["matched"] += 1
                            st["gt_det"] += 1
                            if g["px"] >= 1000:
                                st["gt_det_big"] += 1
                    for j, c in enumerate(kept):
                        if not used[j]:
                            st["fp_px_cat"][cat] += c["px"]

    rows = []
    for cut in CONF_CUTS:
        st = stats[cut]
        rows.append({
            "min_confidence": cut,
            "object_precision": round(st["matched"] / max(st["pred"], 1), 4),
            "recall_big_1000px": round(st["gt_det_big"] / max(gt_big_n, 1), 4),
            "recall_all": round(st["gt_det"] / max(gt_n, 1), 4),
            "pred_components": st["pred"],
            "fp_px_lookalike_M": round(st["fp_px_cat"].get("Lookalike", 0) / 1e6, 2),
        })
        r = rows[-1]
        print(f"conf>={cut:.2f}: obj precision {r['object_precision']:.3f} "
              f"recall(>=10ha) {r['recall_big_1000px']:.3f} "
              f"preds {r['pred_components']} "
              f"lookalike FP px {r['fp_px_lookalike_M']}M")
    Path("analysis/confidence_sweep.json").write_text(json.dumps(
        {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "base": {"checkpoint": CKPT, "threshold": THRESHOLD, "min_area": MIN_AREA},
         "gt_components": gt_n, "gt_big": gt_big_n, "rows": rows,
         "secs": round(time.time() - t0)}, indent=1))
    print("wrote analysis/confidence_sweep.json")


if __name__ == "__main__":
    main()
