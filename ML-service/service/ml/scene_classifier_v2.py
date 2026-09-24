"""OilTrace — stage-1 scene classifier v2: pretrained ResNet-18, RAM-shuffled.

v1 (SceneNet, from scratch) topped out at macro-acc 0.49 — yet even that
weak gate bought +10% object precision at tau=0.8 (MEASURED, gate_eval).
Target here: macro-acc >= 0.85, projecting the gate dial into the 0.80s.

Two measured failure modes shaped this file — do not relearn them:
1. Shard-grouped sampling emits LONG single-class stretches (shards are
   class-segregated by part). Updating BN running stats on those poisons
   them (val collapsed to one class) -> BN is FROZEN (ImageNet stats,
   trainable affine).
2. Even with frozen BN, grouped ordering lets the fast-adapting pretrained
   head TRACK the recent label stream instead of learning features (train
   loss 0.49, val still one class). -> patches are pooled to 2562 and each
   epoch's balanced draw is loaded into RAM (~3 GB), then FULLY SHUFFLED.
   Shards are still read sequentially (one decompression each), so the
   cache-thrash stall v1 fixed stays fixed.

Run:  .venv/Scripts/python.exe -m ml.scene_classifier_v2
Writes runs/C2_scene_r18/best.pth + history.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torchvision.models import (ResNet18_Weights, ResNet34_Weights, resnet18,
                                resnet34)

from ml.patch_dataset import N1_CENTER, N1_SCALE, PatchDataset

_REPO = Path(__file__).resolve().parents[1]
CLASSES = ["Oil", "Lookalike", "No oil"]
BATCH = 64
POOLED = 256


def build_resnet_2ch(backbone: str = "resnet18", n_classes: int = 3,
                     pretrained: bool = True) -> nn.Module:
    weights = (ResNet34_Weights.IMAGENET1K_V1 if pretrained else None)
    weights18 = (ResNet18_Weights.IMAGENET1K_V1 if pretrained else None)
    m = (resnet34(weights=weights) if backbone == "resnet34"
         else resnet18(weights=weights18))
    w = m.conv1.weight.data                      # (64, 3, 7, 7) pretrained
    conv = nn.Conv2d(2, 64, 7, stride=2, padding=3, bias=False)
    # channel-average the RGB filters, rescale so activations keep magnitude
    conv.weight.data = w.mean(1, keepdim=True).repeat(1, 2, 1, 1) * (3 / 2)
    m.conv1 = conv
    m.fc = nn.Linear(m.fc.in_features, n_classes)
    return m


def build_resnet18_2ch(n_classes: int = 3) -> nn.Module:
    """Kept for checkpoint compat (gate_eval loads arch 'resnet18_2ch')."""
    return build_resnet_2ch("resnet18", n_classes)


def freeze_bn(model: nn.Module) -> None:
    """BN layers stay in eval mode (frozen running stats) — see header."""
    for mod in model.modules():
        if isinstance(mod, nn.modules.batchnorm._BatchNorm):
            mod.eval()


def shard_labels(ds: PatchDataset) -> np.ndarray:
    labels = np.zeros(len(ds), dtype=np.int64)
    for fi, f in enumerate(ds.files):
        with np.load(f) as z:
            cats = [CLASSES.index(str(s).split("/")[0]) for s in z["scene"]]
        o = int(ds._offsets[fi])
        labels[o:o + len(cats)] = cats
    return labels


def pool2(img16: np.ndarray) -> np.ndarray:
    """(2,512,512) fp16 raw dB -> (2,256,256) fp16 N1-normalized."""
    x = img16.astype(np.float32).reshape(2, POOLED, 2, POOLED, 2).mean((2, 4))
    return ((x - N1_CENTER) / N1_SCALE).astype(np.float16)


def load_pooled(ds: PatchDataset, picks: np.ndarray, labels: np.ndarray,
                rng: np.random.Generator | None) -> tuple[np.ndarray, np.ndarray]:
    """Load `picks` into a pooled RAM buffer, one shard decompression each,
    optional flip/rot90 augmentation, then a FULL shuffle."""
    buf = np.empty((len(picks), 2, POOLED, POOLED), dtype=np.float16)
    y = labels[picks].copy()
    shard_of = np.searchsorted(ds._offsets, picks, side="right") - 1
    pos = 0
    order = np.argsort(shard_of, kind="stable")   # sequential shard reads
    picks_o, y = picks[order], y[order]
    for fi in np.unique(shard_of):
        sel = picks_o[shard_of[order] == fi] - int(ds._offsets[fi])
        with np.load(ds.files[fi]) as z:
            imgs = z["images"]
            for li in sel:
                p = pool2(imgs[li])
                if rng is not None:               # augment: flips/rot90 only
                    k = int(rng.integers(0, 4))
                    p = np.rot90(p, k, (1, 2))
                    if rng.random() < 0.5:
                        p = p[:, :, ::-1]
                buf[pos] = np.ascontiguousarray(p)
                pos += 1
    assert pos == len(picks)
    perm = (rng or np.random.default_rng(0)).permutation(len(picks))
    return buf[perm], y[perm]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="C2_scene_r18")
    ap.add_argument("--backbone", default="resnet18",
                    choices=["resnet18", "resnet34"])
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--n-per-class", type=int, default=4000)
    ap.add_argument("--lr", type=float, default=1e-4)
    args = ap.parse_args()
    run_dir = _REPO / "runs" / args.run
    n_per_class = args.n_per_class
    torch.manual_seed(26143)
    random.seed(26143)
    np.random.seed(26143)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_ds = PatchDataset(split="train", normalization="N0")
    val_ds = PatchDataset(split="val", normalization="N0")
    tr_labels = shard_labels(train_ds)
    va_labels = shard_labels(val_ds)
    counts = np.bincount(tr_labels, minlength=3)

    print(f"[{args.run}] building val buffer ({len(val_ds)} patches)...",
          flush=True)
    val_x, val_y = load_pooled(val_ds, np.arange(len(val_ds)), va_labels, None)

    model = build_resnet_2ch(args.backbone).to(dev)
    n_par = sum(p.numel() for p in model.parameters()) / 1e6
    print(f"[{args.run}] {n_par:.2f}M params ({args.backbone} ImageNet, frozen BN) · "
          f"train {len(train_ds)} (counts {counts.tolist()}) / "
          f"val {len(val_ds)} · pooled {POOLED}² · {dev}", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")
    ce = nn.CrossEntropyLoss()

    run_dir.mkdir(parents=True, exist_ok=True)
    best_acc, history = -1.0, []
    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        rng = np.random.default_rng(26143 + epoch)
        picks = np.concatenate([
            rng.choice(np.flatnonzero(tr_labels == c),
                       min(n_per_class, counts[c]), replace=False)
            for c in range(3)])
        x, y = load_pooled(train_ds, picks, tr_labels, rng)

        model.train()
        freeze_bn(model)   # must re-apply after every model.train()
        run_loss = nb = 0
        for i in range(0, len(x), BATCH):
            xb = torch.from_numpy(x[i:i+BATCH]).float().to(dev)
            yb = torch.from_numpy(y[i:i+BATCH]).to(dev)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                loss = ce(model(xb), yb)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            run_loss += loss.item()
            nb += 1
        sched.step()

        model.eval()
        conf = np.zeros((3, 3), dtype=np.int64)
        with torch.no_grad():
            for i in range(0, len(val_x), BATCH):
                xb = torch.from_numpy(val_x[i:i+BATCH]).float().to(dev)
                with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                    pred = model(xb).argmax(1).cpu().numpy()
                for t, p in zip(val_y[i:i+BATCH], pred):
                    conf[t, p] += 1
        per_class = conf.diagonal() / conf.sum(1).clip(min=1)
        macro = float(per_class.mean())
        history.append({"epoch": epoch, "loss": run_loss / max(nb, 1),
                        "macro_acc": macro,
                        "per_class_acc": per_class.round(4).tolist(),
                        "confusion": conf.tolist(),
                        "lr": sched.get_last_lr()[0],
                        "secs": round(time.time() - t0)})
        (run_dir / "history.json").write_text(json.dumps(history, indent=1))
        star = ""
        if macro > best_acc:
            best_acc = macro
            torch.save({"model": model.state_dict(), "epoch": epoch,
                        "macro_acc": macro, "classes": CLASSES,
                        "arch": f"{args.backbone}_2ch", "pooled": POOLED},
                       run_dir / "best.pth")
            star = "  *best*"
        print(f"epoch {epoch:2d}  loss {history[-1]['loss']:.4f}  "
              f"macro-acc {macro:.4f}  per-class "
              f"{history[-1]['per_class_acc']}  ({history[-1]['secs']}s){star}",
              flush=True)
    print(f"done · best macro-acc {best_acc:.4f} · {run_dir/'best.pth'}", flush=True)


if __name__ == "__main__":
    main()
