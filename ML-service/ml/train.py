"""OilTrace — experiment trainer (E0 default: U-Net · VV+VH · BCE+Dice · N1).

Frozen-spec mechanics:
- scene-level split via shards (train/val physically separate files)
- AMP fp16 + gradient accumulation → effective batch 16-32 on 6 GB VRAM
- val metrics at provisional threshold 0.5 each epoch (the real threshold
  sweep happens later, on val, after training — spec §07)
- best-val-Dice checkpoint + reproducibility manifest (config, seed, git
  hash, shard coverage) written to runs/<experiment>/

Run:  .venv/Scripts/python.exe -m ml.train --experiment E0
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Sampler

from ml.metrics import PixelMetrics, bce_dice_loss, focal_dice_loss
from ml.model import UNet, count_params
from ml.patch_dataset import PatchDataset

_REPO = Path(__file__).resolve().parents[1]
RUNS = _REPO / "runs"


class ShardAwareSampler(Sampler):
    """Shuffle shard order and indices within each shard, so the dataset's
    small decompressed-shard cache stays hot instead of thrashing."""

    def __init__(self, dataset: PatchDataset, seed: int):
        self.ds = dataset
        self.seed = seed
        self.epoch = 0

    def __len__(self):
        return len(self.ds)

    def __iter__(self):
        rng = random.Random(self.seed + self.epoch)
        self.epoch += 1
        offsets = self.ds._offsets
        shard_order = list(range(len(self.ds.files)))
        rng.shuffle(shard_order)
        for fi in shard_order:
            idxs = list(range(int(offsets[fi]), int(offsets[fi + 1])))
            rng.shuffle(idxs)
            yield from idxs


class BalancedShardSampler(Sampler):
    """Every epoch: ALL oil-positive patches + an equal-ratio random draw of
    negatives, grouped by shard (cache-friendly). Hard negatives still teach
    every epoch, but can no longer drown the oil gradient (the full corpus's
    28% hard-negative share collapsed three cold starts AND a warm start)."""

    def __init__(self, dataset: PatchDataset, seed: int, neg_ratio: float = 1.0):
        self.ds = dataset
        self.seed = seed
        self.neg_ratio = neg_ratio
        self.epoch = 0
        self.flags = dataset.oil_flags()
        self.pos = np.flatnonzero(self.flags)
        self.neg = np.flatnonzero(~self.flags)
        self.n = len(self.pos) + int(len(self.pos) * neg_ratio)

    def __len__(self):
        return self.n

    def __iter__(self):
        rng = np.random.default_rng(self.seed + self.epoch)
        self.epoch += 1
        neg_draw = rng.choice(self.neg, int(len(self.pos) * self.neg_ratio),
                              replace=False)
        idxs = np.concatenate([self.pos, neg_draw])
        # group by shard so the decompressed-shard cache stays hot
        shard_of = np.searchsorted(self.ds._offsets, idxs, side="right") - 1
        order = rng.permutation(len(self.ds.files))
        out = []
        for fi in order:
            grp = idxs[shard_of == fi]
            rng.shuffle(grp)
            out.extend(grp.tolist())
        return iter(out)


def git_hash() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def evaluate(model, loader, dev) -> dict:
    model.eval()
    m = PixelMetrics()
    with torch.no_grad():
        for x, y, _ in loader:
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                logits = model(x)
            m.update(torch.sigmoid(logits.float()) > 0.5, y)
    model.train()
    return m.compute()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="E0")
    ap.add_argument("--norm", default="N1", choices=["N0", "N1", "N2"])
    ap.add_argument("--patch", type=int, default=512)
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--patience", type=int, default=6)
    ap.add_argument("--seed", type=int, default=26143)
    ap.add_argument("--norm-layer", default="batch", choices=["batch", "group"])
    ap.add_argument("--pos-weight", type=float, default=0.0,
                    help="BCE positive-class weight; 0 disables")
    ap.add_argument("--init-from", default=None,
                    help="checkpoint to warm-start model weights from")
    ap.add_argument("--balance", type=float, default=0.0,
                    help="neg:pos patch ratio per epoch; 0 = use all patches")
    ap.add_argument("--loss", default="bce", choices=["bce", "focal"])
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_ds = PatchDataset(split="train", normalization=args.norm,
                            augment=True, patch_size=args.patch, seed=args.seed)
    val_ds = PatchDataset(split="val", normalization=args.norm,
                          augment=False, patch_size=args.patch, seed=args.seed)
    sampler = (BalancedShardSampler(train_ds, args.seed, args.balance)
               if args.balance else ShardAwareSampler(train_ds, args.seed))
    train_loader = DataLoader(train_ds, batch_size=args.batch,
                              sampler=sampler,
                              num_workers=0, pin_memory=dev.type == "cuda")
    val_loader = DataLoader(val_ds, batch_size=args.batch, shuffle=False,
                            num_workers=0, pin_memory=dev.type == "cuda")

    run_dir = RUNS / args.experiment
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "experiment": args.experiment, "config": vars(args),
        "git_hash": git_hash(), "device": str(dev),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "train_patches": len(train_ds), "val_patches": len(val_ds),
        "train_shards": [f.name for f in train_ds.files],
        "val_shards": [f.name for f in val_ds.files],
        "model": "UNet(base=32, norm={})".format(args.norm_layer), "loss": (f"Focal(g=2)+Dice" if args.loss == "focal" else f"BCE(pos_weight={args.pos_weight or None})+Dice(1.0)"),
        "note": "val threshold 0.5 is PROVISIONAL; final threshold from the "
                "post-training val sweep (spec §07)",
    }
    model = UNet(norm=args.norm_layer).to(dev)
    if args.init_from:
        ck = torch.load(args.init_from, map_location=dev, weights_only=False)
        model.load_state_dict(ck["model"])
        manifest["init_from"] = {"path": args.init_from,
                                 "epoch": ck.get("epoch"), "val": ck.get("val")}
        print(f"warm-started from {args.init_from} (epoch {ck.get('epoch')})")
    manifest["params_millions"] = round(count_params(model) / 1e6, 2)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"[{args.experiment}] {manifest['params_millions']}M params · "
          f"train {len(train_ds)} / val {len(val_ds)} patches · {dev}")

    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="max",
                                                       factor=0.5, patience=2)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")

    best_dice, best_epoch = -1.0, -1
    history = []
    if args.init_from:
        v0 = evaluate(model, val_loader, dev)
        print(f"epoch   0 (warm-start eval)  val dice {v0['dice']:.4f} "
              f"iou {v0['iou']:.4f} p {v0['precision']:.4f} r {v0['recall']:.4f}",
              flush=True)
    t0 = time.time()
    for epoch in range(1, args.epochs + 1):
        te = time.time()
        run_loss, nb = 0.0, 0
        opt.zero_grad(set_to_none=True)
        for i, (x, y, _) in enumerate(train_loader):
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                if args.loss == "focal":
                    loss = focal_dice_loss(model(x), y) / args.accum
                else:
                    loss = bce_dice_loss(model(x), y,
                                         pos_weight=args.pos_weight or None) / args.accum
            scaler.scale(loss).backward()
            if (i + 1) % args.accum == 0:
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
            run_loss += float(loss) * args.accum
            nb += 1
        val = evaluate(model, val_loader, dev)
        sched.step(val["dice"])
        history.append({"epoch": epoch, "train_loss": run_loss / max(nb, 1),
                        **{k: val[k] for k in ("dice", "iou", "precision", "recall")},
                        "lr": opt.param_groups[0]["lr"],
                        "secs": round(time.time() - te)})
        (run_dir / "history.json").write_text(json.dumps(history, indent=1))
        star = ""
        if val["dice"] > best_dice:
            best_dice, best_epoch = val["dice"], epoch
            torch.save({"model": model.state_dict(), "epoch": epoch,
                        "val": val, "config": vars(args)},
                       run_dir / "best.pth")
            star = "  *best*"
        print(f"epoch {epoch:3d}  loss {history[-1]['train_loss']:.4f}  "
              f"val dice {val['dice']:.4f} iou {val['iou']:.4f} "
              f"p {val['precision']:.4f} r {val['recall']:.4f}  "
              f"({history[-1]['secs']}s){star}", flush=True)
        if epoch - best_epoch >= args.patience:
            print(f"early stop: no val-Dice gain for {args.patience} epochs")
            break
    print(f"done in {(time.time()-t0)/60:.1f} min · best val Dice "
          f"{best_dice:.4f} @ epoch {best_epoch} · checkpoint {run_dir/'best.pth'}")


if __name__ == "__main__":
    main()
