"""OilTrace — validation threshold sweep (frozen spec §07: threshold is
selected on VALIDATION ONLY, never assumed 0.5, never touched by Part III).

Histogram trick: one forward pass over the val set per checkpoint; oil-pixel
and background-pixel probabilities are histogrammed into fine bins, and
cumulative sums give exact TP/FP/FN — hence Dice/IoU/P/R — for every
threshold at once. Writes analysis/threshold_sweep.json.

Run:  .venv/Scripts/python.exe -m ml.threshold_sweep runs/E0_partial/best.pth runs/E0_finetune/best.pth
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

from ml.inference import load_model
from ml.patch_dataset import PatchDataset

BINS = np.linspace(0.0, 1.0, 201)  # thresholds every 0.005


def sweep(checkpoint: Path, dev: torch.device) -> dict:
    model, meta = load_model(checkpoint, dev)
    ds = PatchDataset(split="val", normalization="N1")
    hist_oil = np.zeros(len(BINS) - 1, dtype=np.int64)
    hist_bg = np.zeros(len(BINS) - 1, dtype=np.int64)
    t0 = time.time()
    with torch.no_grad():
        for i0 in range(0, len(ds), 16):
            xs, ms = [], []
            for i in range(i0, min(i0 + 16, len(ds))):
                img, mask, _ = ds[i]
                xs.append(img)
                ms.append(mask)
            x = torch.stack(xs).to(dev)
            m = torch.stack(ms).to(dev).bool()
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                p = torch.sigmoid(model(x).float())
            po = p[m].cpu().numpy()
            pb = p[~m].cpu().numpy()
            hist_oil += np.histogram(po, bins=BINS)[0]
            hist_bg += np.histogram(pb, bins=BINS)[0]
    n_oil = int(hist_oil.sum())
    # pred positive at threshold t = pixels with prob >= t = suffix sums
    tp = np.cumsum(hist_oil[::-1])[::-1]
    fp = np.cumsum(hist_bg[::-1])[::-1]
    fn = n_oil - tp
    thresholds = BINS[:-1]
    dice = np.where(2 * tp + fp + fn > 0, 2 * tp / np.maximum(2 * tp + fp + fn, 1), 0)
    iou = np.where(tp + fp + fn > 0, tp / np.maximum(tp + fp + fn, 1), 0)
    prec = np.where(tp + fp > 0, tp / np.maximum(tp + fp, 1), 0)
    rec = np.where(tp + fn > 0, tp / np.maximum(tp + fn, 1), 0)
    bi = int(dice.argmax())
    out = {
        "checkpoint": str(checkpoint), "epoch": meta["epoch"],
        "val_at_0.5": meta["val"],
        "best": {"threshold": float(thresholds[bi]), "dice": float(dice[bi]),
                 "iou": float(iou[bi]), "precision": float(prec[bi]),
                 "recall": float(rec[bi])},
        "curve_every_0.05": [
            {"t": round(float(t), 2), "dice": round(float(d), 4),
             "p": round(float(pp), 4), "r": round(float(rr), 4)}
            for t, d, pp, rr in zip(thresholds[::10], dice[::10],
                                    prec[::10], rec[::10])],
        "secs": round(time.time() - t0),
    }
    print(f"{checkpoint}: best t={out['best']['threshold']:.3f} -> "
          f"dice {out['best']['dice']:.4f} (p {out['best']['precision']:.3f} "
          f"r {out['best']['recall']:.3f}) [{out['secs']}s]")
    return out


def main():
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    results = [sweep(Path(c), dev) for c in sys.argv[1:]]
    out = Path("analysis/threshold_sweep.json")
    out.write_text(json.dumps({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                               "note": "selected on validation only; Part III untouched",
                               "results": results}, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
