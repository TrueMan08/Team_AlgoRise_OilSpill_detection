"""OilTrace — baselines A and B (frozen spec §07): the anchor numbers every
model result is measured against.

A — all-background: predict 0 everywhere. Dice/IoU/recall are 0 by
    construction whenever oil exists; its value is showing the FP-free
    precision ceiling and making "better than nothing" quantitative.
B — VV threshold: pixel is oil if VV < t dB. t is selected on TRAIN patches
    only (Dice sweep), then evaluated once on val. The measured Part III
    facts (+0.09 dB median contrast) predict this baseline fails — B exists
    to prove the failure with numbers, not to compete.

Writes analysis/baselines.json. Uses whatever shards exist; records shard
coverage so provisional runs are labeled as such.

Run:  .venv/Scripts/python.exe -m ml.baselines
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import torch

from ml.metrics import PixelMetrics
from ml.patch_dataset import PatchDataset

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "analysis" / "baselines.json"
THRESHOLDS = np.arange(-40.0, -10.0, 0.5)  # dB sweep range for baseline B


def _iter_split(split: str, batch: int = 64):
    ds = PatchDataset(split=split, normalization="N0", augment=False)
    n = len(ds)
    for i0 in range(0, n, batch):
        imgs, masks = [], []
        for i in range(i0, min(i0 + batch, n)):
            img, mask, _ = ds[i]
            imgs.append(img)
            masks.append(mask)
        yield torch.stack(imgs), torch.stack(masks)


def baseline_a(split: str) -> dict:
    m = PixelMetrics()
    for imgs, masks in _iter_split(split):
        m.update(torch.zeros_like(masks), masks)
    return m.compute()


def select_threshold_on_train() -> tuple[float, dict]:
    """Sweep VV thresholds on TRAIN, pick best Dice (val never touched).

    Exact for every candidate threshold in ONE pass: histogram oil and
    non-oil VV values into 0.5 dB bins; cumulative sums below each bin edge
    give TP/FP (and total-oil gives FN)."""
    edges = np.concatenate([THRESHOLDS, [THRESHOLDS[-1] + 0.5]])
    hist_oil = np.zeros(len(THRESHOLDS) + 1, dtype=np.int64)
    hist_bg = np.zeros(len(THRESHOLDS) + 1, dtype=np.int64)
    extended = np.concatenate([[-1e9], edges, [1e9]])
    n_oil = 0
    for imgs, masks in _iter_split("train"):
        vv = imgs[:, 0].numpy().ravel()
        oil = masks[:, 0].numpy().ravel().astype(bool)
        n_oil += int(oil.sum())
        hist_oil = hist_oil + np.histogram(vv[oil], bins=extended)[0][: len(hist_oil)]
        hist_bg = hist_bg + np.histogram(vv[~oil], bins=extended)[0][: len(hist_bg)]
    # pixels with value < THRESHOLDS[i] = cumulative count of bins 0..i-1
    tp = np.cumsum(hist_oil)[: len(THRESHOLDS)]
    fp = np.cumsum(hist_bg)[: len(THRESHOLDS)]
    fn = n_oil - tp
    denom = 2 * tp + fp + fn
    dice = np.where(denom > 0, 2 * tp / np.maximum(denom, 1), 0.0)
    bi = int(dice.argmax())
    best = float(THRESHOLDS[bi])
    return best, {"train_dice_at_best": float(dice[bi]),
                  "sweep": {f"{t:.1f}": round(float(s), 4)
                            for t, s in zip(THRESHOLDS, dice)}}


def baseline_b(split: str, thr: float) -> dict:
    m = PixelMetrics()
    for imgs, masks in _iter_split(split):
        m.update(imgs[:, 0:1] < thr, masks)
    return m.compute()


def main():
    t0 = time.time()
    train_ds = PatchDataset(split="train", normalization="N0")
    val_ds = PatchDataset(split="val", normalization="N0")
    coverage = {"train_patches": len(train_ds), "val_patches": len(val_ds),
                "train_shards": len(train_ds.files), "val_shards": len(val_ds.files)}
    print(f"coverage: {coverage}")

    print("baseline A (all-background) on val ...")
    a = baseline_a("val")
    print(f"  A: {a}")

    print("baseline B: selecting VV threshold on TRAIN ...")
    thr, sel = select_threshold_on_train()
    print(f"  selected t = {thr:.1f} dB (train Dice {sel['train_dice_at_best']:.4f})")
    b = baseline_b("val", thr)
    print(f"  B on val: {b}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "shard_coverage": coverage,
        "provisional": "true if shard run incomplete when generated",
        "baseline_A_all_background": {"val": a},
        "baseline_B_vv_threshold": {"selected_threshold_dB": thr,
                                    "selection": sel, "val": b},
    }, indent=1))
    print(f"wrote {OUT} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
