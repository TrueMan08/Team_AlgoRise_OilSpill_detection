"""OilTrace — EXTERNAL GENERALIZATION spot-check on the refined Deep-SAR
Oil Spill (SOS) dataset (Zenodo 15298010, CC-BY 4.0). Inference-only —
nothing here may tune our pipeline.

Honest domain-shift caveats (report them with any number):
- SOS patches are 8-bit amplitude images (PALSAR L-band + Sentinel-1),
  not our calibrated VV+VH Sigma0-dB pairs.
- Adapter (documented hack): grayscale 0..255 -> linear map onto our
  measured dB envelope [-35, 0], duplicated into both channels, then N1.
- We report (a) metrics at OUR frozen threshold 0.325 and (b) the
  best-threshold-on-SOS as an ORACLE UPPER BOUND (not our claim).
- Subsets split by path substring (palsar / sentinel) and reported
  separately — Sentinel-1 is the comparable one.

Run (after run_sos_eval.ps1 extracts the zips):
  .venv/Scripts/python.exe -m ml.eval_sos
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

ROOT = Path("external/sos")
CKPT = Path("runs/E5_focal/best.pth")
FROZEN_T = 0.325
DB_LO, DB_HI = -35.0, 0.0
N1_CENTER, N1_SCALE = -17.5, 17.5
BINS = np.linspace(0, 1, 201)
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def find_pairs() -> list[tuple[Path, Path, str]]:
    imgs = {p.stem: p for p in ROOT.rglob("*")
            if p.suffix.lower() in IMG_EXT and "mask" not in str(p).lower()
            and "images" in str(p).lower()}
    masks = {p.stem: p for p in ROOT.rglob("*")
             if p.suffix.lower() in IMG_EXT and "mask" in str(p).lower()}
    pairs = []
    for stem, ip in imgs.items():
        mp = masks.get(stem)
        if mp is None:
            continue
        s = str(ip).lower()
        subset = ("palsar" if "palsar" in s or "alos" in s else
                  "sentinel" if "sentinel" in s else "unknown")
        pairs.append((ip, mp, subset))
    return pairs


def main():
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, meta = load_model(CKPT, dev)
    pairs = find_pairs()
    print(f"paired samples: {len(pairs)} "
          f"({dict((s, sum(1 for _,_,x in pairs if x==s)) for s in set(p[2] for p in pairs))})")
    if not pairs:
        raise SystemExit("no image/mask pairs found under external/sos — check extraction")

    acc = defaultdict(lambda: {"ho": np.zeros(len(BINS)-1, np.int64),
                               "hb": np.zeros(len(BINS)-1, np.int64)})
    t0 = time.time()
    B = 32
    for i0 in range(0, len(pairs), B):
        chunk = pairs[i0:i0+B]
        xs, ms, subs = [], [], []
        for ip, mp, sub in chunk:
            g = cv2.imread(str(ip), cv2.IMREAD_GRAYSCALE)
            m = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
            if g is None or m is None or g.shape != m.shape:
                continue
            h, w = (g.shape[0] // 16) * 16, (g.shape[1] // 16) * 16
            g, m = g[:h, :w], m[:h, :w]
            db = DB_LO + (g.astype(np.float32) / 255.0) * (DB_HI - DB_LO)
            x = (np.stack([db, db]) - N1_CENTER) / N1_SCALE
            xs.append(torch.from_numpy(x))
            ms.append(m > 127)
            subs.append(sub)
        if not xs:
            continue
        xb = torch.stack(xs).to(dev)
        with torch.no_grad(), torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
            p = torch.sigmoid(model(xb).float())[:, 0].cpu().numpy()
        for prob, mask, sub in zip(p, ms, subs):
            acc[sub]["ho"] += np.histogram(prob[mask], bins=BINS)[0]
            acc[sub]["hb"] += np.histogram(prob[~mask], bins=BINS)[0]
        if (i0 // B) % 20 == 0:
            print(f"  {i0+len(chunk)}/{len(pairs)} ({time.time()-t0:.0f}s)")

    def metrics(ho, hb):
        n_oil = int(ho.sum())
        tp = np.cumsum(ho[::-1])[::-1]
        fp = np.cumsum(hb[::-1])[::-1]
        fn = n_oil - tp
        dice = np.where(2*tp+fp+fn > 0, 2*tp/np.maximum(2*tp+fp+fn, 1), 0.0)
        ti = int(np.searchsorted(BINS[:-1], FROZEN_T))
        bi = int(dice.argmax())
        f = lambda i: {"threshold": float(BINS[:-1][i]), "dice": float(dice[i]),
                       "precision": float(tp[i]/max(tp[i]+fp[i], 1)),
                       "recall": float(tp[i]/max(n_oil, 1))}
        return {"at_frozen_0.325": f(ti), "oracle_best": f(bi),
                "oil_pixels": n_oil}

    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "checkpoint": str(CKPT),
           "note": "EXTERNAL generalization, inference-only; 8-bit amplitude "
                   "mapped linearly to [-35,0] dB and duplicated to 2ch — a "
                   "documented domain-shift hack. Oracle row = upper bound, "
                   "not our claim.",
           "subsets": {}}
    for sub, h in acc.items():
        r = metrics(h["ho"], h["hb"])
        out["subsets"][sub] = r
        print(f"{sub:9s}: frozen-t dice {r['at_frozen_0.325']['dice']:.3f} "
              f"(p {r['at_frozen_0.325']['precision']:.3f} r {r['at_frozen_0.325']['recall']:.3f}) "
              f"| oracle dice {r['oracle_best']['dice']:.3f} @ t={r['oracle_best']['threshold']:.2f}")
    Path("analysis/sos_external_eval.json").write_text(json.dumps(out, indent=1))
    print(f"wrote analysis/sos_external_eval.json ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
