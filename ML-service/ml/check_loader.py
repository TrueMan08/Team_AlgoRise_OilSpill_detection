"""OilTrace — loader verification (exit criteria for dev-sequence steps 1–3).

Two modes:
  python -m ml.check_loader            # quick: 6 fixture scenes (2 per category)
                                       # -> analysis/loader_batch_check.png
  python -m ml.check_loader --sweep    # full: alignment assertions on all 450
                                       # pairs (no figures; ~minutes)

Exit criteria proven here:
  step 1: DataLoader collates a batch of [2,2048,2048] raw-dB tensors correctly
  step 2: VV / VH / mask / overlay panels render sanely (2–98% dB stretch)
  step 3: alignment assertions pass on every scene touched
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.loader import DEFAULT_ROOT, CATEGORIES, SceneDataset, discover_pairs

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "analysis"


def stretch(band: np.ndarray, lo_p: float = 2, hi_p: float = 98) -> np.ndarray:
    lo, hi = np.percentile(band, [lo_p, hi_p])
    return np.clip((band - lo) / max(hi - lo, 1e-6), 0, 1)


def quick_batch() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pairs = discover_pairs()
    fixtures = []
    for cat in CATEGORIES:
        cat_pairs = [p for p in pairs if p.category == cat][:2]
        fixtures.extend(cat_pairs)
    ds = SceneDataset(fixtures)

    def collate(items):
        imgs = torch.stack([i[0] for i in items])
        masks = torch.stack([i[1] for i in items])
        metas = [i[2] for i in items]
        return imgs, masks, metas

    dl = DataLoader(ds, batch_size=len(fixtures), collate_fn=collate)
    imgs, masks, metas = next(iter(dl))

    # step-1 exit: batch shape/dtype exactly as the frozen contract demands
    assert imgs.shape == (len(fixtures), 2, 2048, 2048), imgs.shape
    assert imgs.dtype == torch.float32 and masks.dtype == torch.uint8
    print(f"batch OK: images {tuple(imgs.shape)} float32 raw dB "
          f"(range {imgs.min():.1f}..{imgs.max():.1f}), masks {tuple(masks.shape)} uint8")

    n = len(fixtures)
    fig, axes = plt.subplots(n, 4, figsize=(16, 4 * n))
    for r in range(n):
        vv, vh = imgs[r, 0].numpy(), imgs[r, 1].numpy()
        m = masks[r].numpy()
        svv = stretch(vv)
        panels = [(svv, f"{metas[r]['category']} {metas[r]['scene_id']} — VV (dB)"),
                  (stretch(vh), "VH (dB)"), (m, f"mask ({m.mean()*100:.2f}% oil)")]
        for c, (img, title) in enumerate(panels):
            axes[r, c].imshow(img, cmap="gray", interpolation="nearest")
            axes[r, c].set_title(title, fontsize=9)
        overlay = np.stack([svv] * 3, axis=-1)
        overlay[m == 1] = [1.0, 0.25, 0.0]
        axes[r, 3].imshow(overlay, interpolation="nearest")
        axes[r, 3].set_title("VV + mask overlay", fontsize=9)
        for c in range(4):
            axes[r, c].axis("off")
    OUT.mkdir(exist_ok=True)
    out = OUT / "loader_batch_check.png"
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")


def full_sweep() -> None:
    ds = SceneDataset()
    print(f"sweeping {len(ds)} pairs under {DEFAULT_ROOT}")
    t0, bad = time.time(), []
    per_cat: dict[str, int] = {}
    for i in range(len(ds)):
        try:
            _, mask, meta = ds[i]
            per_cat[meta["category"]] = per_cat.get(meta["category"], 0) + 1
            if meta["category"] != "Oil" and mask.any():
                bad.append((meta["path"], "negative scene has nonzero mask"))
        except Exception as e:  # AlignmentError or read failure — both count
            bad.append((ds.pairs[i].image_path, str(e)[:100]))
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(ds)} ({time.time()-t0:.0f}s)")
    print(f"done in {time.time()-t0:.0f}s · per category: {per_cat}")
    if bad:
        print(f"FAILURES: {len(bad)}")
        for p, e in bad[:20]:
            print("  ", p, "→", e)
        sys.exit(1)
    print("all scenes pass the alignment contract")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="assert on all 450 pairs")
    args = ap.parse_args()
    full_sweep() if args.sweep else quick_batch()
