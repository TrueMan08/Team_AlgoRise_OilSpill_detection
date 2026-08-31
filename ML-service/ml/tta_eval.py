"""OilTrace — same-day accuracy levers, measured on validation:
(a) E0_finetune alone            (baseline: Dice 0.3463 @ t=0.325)
(b) + 8-way TTA (flips/rot90 — the frozen spec's augmentation group)
(c) ensemble: mean prob of E0_partial + E0_finetune
(d) ensemble + TTA
Each variant gets an exact all-thresholds sweep via probability histograms.

Run:  .venv/Scripts/python.exe -m ml.tta_eval
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import torch

from ml.inference import load_model
from ml.patch_dataset import PatchDataset

BINS = np.linspace(0.0, 1.0, 201)


def tta_prob(model, x: torch.Tensor, dev) -> torch.Tensor:
    """Mean sigmoid over the 8 flip/rot90 variants (dihedral group)."""
    acc = None
    for k in range(4):
        xr = torch.rot90(x, k, (2, 3))
        for flip in (False, True):
            xi = torch.flip(xr, (3,)) if flip else xr
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                p = torch.sigmoid(model(xi).float())
            if flip:
                p = torch.flip(p, (3,))
            p = torch.rot90(p, -k, (2, 3))
            acc = p if acc is None else acc + p
    return acc / 8


def evaluate(models, use_tta: bool, dev) -> dict:
    ds = PatchDataset(split="val", normalization="N1")
    hist_oil = np.zeros(len(BINS) - 1, dtype=np.int64)
    hist_bg = np.zeros(len(BINS) - 1, dtype=np.int64)
    with torch.no_grad():
        for i0 in range(0, len(ds), 8):
            xs, ms = [], []
            for i in range(i0, min(i0 + 8, len(ds))):
                img, mask, _ = ds[i]
                xs.append(img)
                ms.append(mask)
            x = torch.stack(xs).to(dev)
            m = torch.stack(ms).to(dev).bool()
            probs = []
            for model in models:
                if use_tta:
                    probs.append(tta_prob(model, x, dev))
                else:
                    with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                        probs.append(torch.sigmoid(model(x).float()))
            p = torch.stack(probs).mean(0)
            hist_oil += np.histogram(p[m].cpu().numpy(), bins=BINS)[0]
            hist_bg += np.histogram(p[~m].cpu().numpy(), bins=BINS)[0]
    n_oil = int(hist_oil.sum())
    tp = np.cumsum(hist_oil[::-1])[::-1]
    fp = np.cumsum(hist_bg[::-1])[::-1]
    fn = n_oil - tp
    dice = np.where(2 * tp + fp + fn > 0, 2 * tp / np.maximum(2 * tp + fp + fn, 1), 0)
    bi = int(dice.argmax())
    return {"threshold": float(BINS[bi]), "dice": float(dice[bi]),
            "precision": float(tp[bi] / max(tp[bi] + fp[bi], 1)),
            "recall": float(tp[bi] / max(n_oil, 1))}


def main():
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ft, _ = load_model(Path("runs/E0_finetune/best.pth"), dev)
    pt, _ = load_model(Path("runs/E0_partial/best.pth"), dev)
    results = {}
    for name, models, tta in [
        ("finetune", [ft], False),
        ("finetune+TTA", [ft], True),
        ("ensemble", [pt, ft], False),
        ("ensemble+TTA", [pt, ft], True),
    ]:
        t0 = time.time()
        r = evaluate(models, tta, dev)
        r["secs"] = round(time.time() - t0)
        results[name] = r
        print(f"{name:14s}: dice {r['dice']:.4f} @ t={r['threshold']:.3f} "
              f"(p {r['precision']:.3f} r {r['recall']:.3f}) [{r['secs']}s]")
    Path("analysis/tta_eval.json").write_text(json.dumps(
        {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "baseline_note": "finetune @ 0.325 = 0.3463", "results": results}, indent=1))
    print("wrote analysis/tta_eval.json")


if __name__ == "__main__":
    main()
