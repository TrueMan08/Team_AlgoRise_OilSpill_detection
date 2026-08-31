"""OilTrace — step 6b smoke test (frozen spec): overfit ~10 oil patches to
Dice ≈ 1.0. If the U-Net cannot memorize 10 patches, something is broken in
the loss / loader / mask polarity — catch it before burning GPU-hours on E0.

Pass criterion: Dice >= 0.95 within 400 iterations.

Run:  .venv/Scripts/python.exe -m ml.smoke_test
"""
from __future__ import annotations

import time

import numpy as np
import torch

from ml.metrics import PixelMetrics, bce_dice_loss
from ml.model import UNet, count_params
from ml.patch_dataset import PatchDataset

N_PATCHES = 10
MAX_ITERS = 400
TARGET_DICE = 0.95


def main():
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {dev} ({torch.cuda.get_device_name(0) if dev.type=='cuda' else 'cpu'})")

    ds = PatchDataset(split="train", normalization="N1", augment=False)
    # pick the first N patches that actually contain oil
    imgs, masks = [], []
    for i in range(len(ds)):
        img, mask, _ = ds[i]
        if mask.any():
            imgs.append(img)
            masks.append(mask)
        if len(imgs) == N_PATCHES:
            break
    assert len(imgs) == N_PATCHES, f"only {len(imgs)} oil patches found"
    x = torch.stack(imgs).to(dev)
    y = torch.stack(masks).to(dev)
    print(f"overfitting {N_PATCHES} patches, oil fraction "
          f"{float(y.mean()):.4f}")

    model = UNet().to(dev)
    print(f"UNet params: {count_params(model)/1e6:.2f} M")
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")

    t0 = time.time()
    for it in range(1, MAX_ITERS + 1):
        opt.zero_grad(set_to_none=True)
        with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
            logits = model(x)
            loss = bce_dice_loss(logits, y)
        scaler.scale(loss).backward()
        scaler.step(opt)
        scaler.update()
        if it % 25 == 0 or it == 1:
            with torch.no_grad():
                m = PixelMetrics()
                m.update(torch.sigmoid(logits) > 0.5, y)
                d = m.compute()["dice"]
            print(f"iter {it:4d}  loss {float(loss):.4f}  dice {d:.4f}  "
                  f"({time.time()-t0:.0f}s)")
            if d >= TARGET_DICE:
                print(f"SMOKE TEST PASSED: dice {d:.4f} >= {TARGET_DICE} "
                      f"at iter {it} in {time.time()-t0:.0f}s")
                if dev.type == "cuda":
                    print(f"peak VRAM: {torch.cuda.max_memory_allocated()/1e9:.2f} GB")
                return
    raise SystemExit(f"SMOKE TEST FAILED: dice never reached {TARGET_DICE} "
                     f"in {MAX_ITERS} iters — check loss/loader/mask polarity")


if __name__ == "__main__":
    main()
