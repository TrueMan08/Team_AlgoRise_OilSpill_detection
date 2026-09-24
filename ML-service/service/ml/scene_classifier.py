"""OilTrace — stage-1 scene-context classifier (two-stage architecture).

Classifies each 512² patch by its SCENE category {Oil, Lookalike, No oil} —
the labels come free from the shard metadata. At serving time, per-tile
"trap" probabilities gate the segmentation output (stage 2), attacking the
diagnosed disease: confident look-alike false positives.

Design notes:
- labels are scene-level, so patch labels are weakly noisy (an empty-ocean
  patch from an Oil scene looks like No-oil) — acceptable: the classes we
  must separate well are Lookalike-hardneg vs Oil, which are exactly the
  patches sampled into the shards.
- encoder reuses the project's DoubleConv blocks; ~2M params, trains in
  minutes/epoch on the 4050. No external pretrained weights (kept
  dependency-free deliberately).

Run:  .venv/Scripts/python.exe -m ml.scene_classifier
Writes runs/C1_scene/best.pth + history.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from ml.model import DoubleConv
from ml.patch_dataset import PatchDataset

_REPO = Path(__file__).resolve().parents[1]
RUN = _REPO / "runs" / "C1_scene"
CLASSES = ["Oil", "Lookalike", "No oil"]


class SceneNet(nn.Module):
    def __init__(self, in_ch: int = 2, base: int = 24, n_classes: int = 3):
        super().__init__()
        c = [base, base * 2, base * 4, base * 8]
        self.features = nn.Sequential(
            DoubleConv(in_ch, c[0]), nn.MaxPool2d(2),
            DoubleConv(c[0], c[1]), nn.MaxPool2d(2),
            DoubleConv(c[1], c[2]), nn.MaxPool2d(2),
            DoubleConv(c[2], c[3]), nn.AdaptiveAvgPool2d(1),
        )
        self.head = nn.Linear(c[3], n_classes)

    def forward(self, x):
        return self.head(self.features(x).flatten(1))


class LabeledPatches(Dataset):
    def __init__(self, split: str, augment: bool = False):
        self.ds = PatchDataset(split=split, normalization="N1", augment=augment)
        self.labels = np.zeros(len(self.ds), dtype=np.int64)
        for fi, f in enumerate(self.ds.files):
            with np.load(f) as z:
                cats = [CLASSES.index(str(s).split("/")[0]) for s in z["scene"]]
            o = int(self.ds._offsets[fi])
            self.labels[o:o + len(cats)] = cats

    def __len__(self):
        return len(self.ds)

    def __getitem__(self, i):
        img, _, _ = self.ds[i]
        return img, int(self.labels[i])


def main():
    torch.manual_seed(26143)
    random.seed(26143)
    np.random.seed(26143)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train = LabeledPatches("train", augment=True)
    val = LabeledPatches("val")
    # class-balanced, SHARD-AWARE sampling: random indices across compressed
    # shards thrash the 2-shard cache (one decompression per sample) — group
    # each epoch's balanced draw by shard instead.
    counts = np.bincount(train.labels, minlength=3)

    class BalancedShardSampler(torch.utils.data.Sampler):
        def __init__(self, labels, offsets, n_per_class=4000, seed=26143):
            self.labels, self.offsets = labels, offsets
            self.n_per_class, self.epoch, self.seed = n_per_class, 0, seed

        def __len__(self):
            return sum(min(self.n_per_class, c) for c in counts)

        def __iter__(self):
            rng = np.random.default_rng(self.seed + self.epoch)
            self.epoch += 1
            picks = np.concatenate([
                rng.choice(np.flatnonzero(self.labels == c),
                           min(self.n_per_class, counts[c]), replace=False)
                for c in range(3)])
            shard_of = np.searchsorted(self.offsets, picks, side="right") - 1
            order = rng.permutation(int(shard_of.max()) + 1)
            out = []
            for fi in order:
                grp = picks[shard_of == fi]
                rng.shuffle(grp)
                out.extend(grp.tolist())
            return iter(out)

    sampler = BalancedShardSampler(train.labels, train.ds._offsets)
    tl = DataLoader(train, batch_size=24, sampler=sampler, num_workers=0,
                    pin_memory=dev.type == "cuda")
    vl = DataLoader(val, batch_size=48, shuffle=False, num_workers=0)

    model = SceneNet().to(dev)
    n_par = sum(p.numel() for p in model.parameters()) / 1e6
    print(f"[C1_scene] {n_par:.2f}M params · train {len(train)} "
          f"(counts {counts.tolist()}) / val {len(val)} · {dev}", flush=True)
    opt = torch.optim.Adam(model.parameters(), lr=3e-4)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")
    ce = nn.CrossEntropyLoss()

    RUN.mkdir(parents=True, exist_ok=True)
    best_acc, history = -1.0, []
    for epoch in range(1, 9):
        t0 = time.time()
        model.train()
        run_loss = nb = 0
        for x, y in tl:
            x, y = x.to(dev), y.to(dev)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                loss = ce(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            run_loss += loss.item()
            nb += 1
        model.eval()
        conf = np.zeros((3, 3), dtype=np.int64)
        with torch.no_grad():
            for x, y in vl:
                with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                    pred = model(x.to(dev)).argmax(1).cpu().numpy()
                for t, p in zip(y.numpy(), pred):
                    conf[t, p] += 1
        per_class = conf.diagonal() / conf.sum(1).clip(min=1)
        macro = float(per_class.mean())
        history.append({"epoch": epoch, "loss": run_loss / max(nb, 1),
                        "macro_acc": macro,
                        "per_class_acc": per_class.round(4).tolist(),
                        "confusion": conf.tolist(),
                        "secs": round(time.time() - t0)})
        (RUN / "history.json").write_text(json.dumps(history, indent=1))
        star = ""
        if macro > best_acc:
            best_acc = macro
            torch.save({"model": model.state_dict(), "epoch": epoch,
                        "macro_acc": macro, "classes": CLASSES},
                       RUN / "best.pth")
            star = "  *best*"
        print(f"epoch {epoch}  loss {history[-1]['loss']:.4f}  "
              f"macro-acc {macro:.4f}  per-class "
              f"{history[-1]['per_class_acc']}  ({history[-1]['secs']}s){star}",
              flush=True)
    print(f"done · best macro-acc {best_acc:.4f} · {RUN/'best.pth'}", flush=True)


if __name__ == "__main__":
    main()
