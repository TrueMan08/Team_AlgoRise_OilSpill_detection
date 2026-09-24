"""OilTrace — component verifier (Phase 4.2): learned per-alert scoring.

Replaces the crude morphological-close/confidence rules with a calibrated
logistic model over component features. The fragmentation diagnosis: many
of X1c's "false positives" are fragments and faint edges — features like
fragment density, shape, contrast and the stage-1 gate probability separate
them from real slicks better than any single cutoff.

DISCIPLINE: the verifier is FIT ON TRAIN PATCHES ONLY (segmenter + gate
run over the v2 train shards, components matched against train masks).
The val set only ever judges the finished scorer — same seal ethics as
everything else.

Features per component (t=0.8 mask, >=250 px):
  log_area, mean_prob, max_prob, prob_std, solidity, elongation,
  n_comps_in_patch, pred_frac_of_patch, p_lookalike (C3), vv_contrast_db,
  touches_border

Run:  OILTRACE_SHARDS=... python -m ml.verifier fit    (train + save)
      OILTRACE_SHARDS=... python -m ml.verifier eval   (val P/R sweep)
Writes runs/V1_verifier/{weights.json,report.json}.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from ml.gate_eval import comps, load_classifier
from ml.inference import load_model
from ml.patch_dataset import PatchDataset

_REPO = Path(__file__).resolve().parents[1]
RUN = _REPO / "runs" / "V1_verifier"
SEG = "runs/X1c_r34_strict/best.pth"
CLF = "runs/C3_scene_r34/best.pth"
T = 0.8
MIN_AREA = 250
FEATS = ["log_area", "mean_prob", "max_prob", "prob_std", "solidity",
         "elongation", "n_comps", "pred_frac", "p_lookalike",
         "vv_contrast_db", "touches_border"]


def comp_features(c, prob, img_vv, n_comps, pred_frac, p_lk):
    m = c["mask"]
    ys, xs = np.nonzero(m)
    pts = np.column_stack([xs, ys]).astype(np.int32)
    hull = cv2.convexHull(pts)
    solidity = c["px"] / max(cv2.contourArea(hull), c["px"])
    (_, (w, h), _) = cv2.minAreaRect(pts)
    elong = (min(w, h) + 1) / (max(w, h) + 1)
    ring = cv2.dilate(m.astype(np.uint8),
                      cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))) \
        .astype(bool) & ~m
    contrast = float(img_vv[m].mean() - (img_vv[ring].mean() if ring.any()
                                         else img_vv.mean()))
    border = float(ys.min() == 0 or xs.min() == 0 or
                   ys.max() == prob.shape[0] - 1 or xs.max() == prob.shape[1] - 1)
    return [np.log10(c["px"]), float(prob[m].mean()), float(prob[m].max()),
            float(prob[m].std()), float(solidity), float(elong),
            float(n_comps), float(pred_frac), float(p_lk), contrast, border]


def collect(split: str, limit: int | None = None):
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    seg, _ = load_model(Path(SEG), dev)
    clf, ck = load_classifier(CLF, dev)
    lk = ck["classes"].index("Lookalike")
    ds = PatchDataset(split=split, normalization="N1")
    n = len(ds) if limit is None else min(limit, len(ds))
    X, y = [], []
    t0 = time.time()
    with torch.no_grad():
        for i0 in range(0, n, 16):
            xs, ms = [], []
            for i in range(i0, min(i0 + 16, n)):
                img, mask, _ = ds[i]
                xs.append(img)
                ms.append(mask[0].numpy().astype(np.uint8))
            xb = torch.stack(xs).to(dev)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                probs = torch.sigmoid(seg(xb).float())[:, 0].cpu().numpy()
                plk = torch.softmax(clf(xb).float(), 1)[:, lk].cpu().numpy()
            vv = (xb[:, 0].cpu().numpy() * 17.5) - 17.5   # de-normalize N1
            for prob, gt, p_lk, img_vv in zip(probs, ms, plk, vv):
                pred = (prob > T).astype(np.uint8)
                if not pred.any():
                    continue
                pc = [c for c in comps(pred) if c["px"] >= MIN_AREA]
                if not pc:
                    continue
                gc = comps(gt) if gt.any() else []
                pred_frac = pred.mean()
                for c in pc:
                    matched = 0
                    for g in gc:
                        inter = np.logical_and(g["mask"], c["mask"]).sum()
                        if inter and inter / (g["px"] + c["px"] - inter) >= 0.1:
                            matched = 1
                            break
                    X.append(comp_features(c, prob, img_vv, len(pc),
                                           pred_frac, p_lk))
                    y.append(matched)
            if (i0 // 16) % 100 == 0:
                print(f"  {split} {i0}/{n} patches · {len(y)} comps "
                      f"({time.time()-t0:.0f}s)", flush=True)
    return np.array(X, dtype=np.float64), np.array(y, dtype=np.float64)


def fit():
    RUN.mkdir(parents=True, exist_ok=True)
    X, y = collect("train")
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = torch.tensor((X - mu) / sd)
    yt = torch.tensor(y)
    w = torch.zeros(X.shape[1], dtype=torch.float64, requires_grad=True)
    b = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([w, b], max_iter=200)

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            Xs @ w + b, yt) + 1e-4 * (w ** 2).sum()
        loss.backward()
        return loss
    opt.step(closure)
    out = {"seg": SEG, "clf": CLF, "threshold": T, "min_area": MIN_AREA,
           "features": FEATS, "mu": mu.tolist(), "sd": sd.tolist(),
           "w": w.detach().tolist(), "b": float(b.detach()),
           "train_comps": int(len(y)), "train_pos_frac": float(y.mean())}
    (RUN / "weights.json").write_text(json.dumps(out, indent=1))
    print(f"fit on {len(y)} train comps (pos {y.mean():.1%}) · "
          f"weights -> {RUN/'weights.json'}")
    for f, wi in sorted(zip(FEATS, w.detach().tolist()), key=lambda t: -abs(t[1])):
        print(f"  {f:15s} {wi:+.3f}")


def evaluate():
    wj = json.loads((RUN / "weights.json").read_text())
    mu, sd = np.array(wj["mu"]), np.array(wj["sd"])
    w, b = np.array(wj["w"]), wj["b"]
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    seg, _ = load_model(Path(SEG), dev)
    clf, ck = load_classifier(CLF, dev)
    lk = ck["classes"].index("Lookalike")
    ds = PatchDataset(split="val", normalization="N1")

    rows_stats = {s: {"pred": 0, "matched": 0, "big": 0}
                  for s in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]}
    gt_big = 0
    with torch.no_grad():
        for i0 in range(0, len(ds), 16):
            xs, ms = [], []
            for i in range(i0, min(i0 + 16, len(ds))):
                img, mask, _ = ds[i]
                xs.append(img)
                ms.append(mask[0].numpy().astype(np.uint8))
            xb = torch.stack(xs).to(dev)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                probs = torch.sigmoid(seg(xb).float())[:, 0].cpu().numpy()
                plk = torch.softmax(clf(xb).float(), 1)[:, lk].cpu().numpy()
            vv = (xb[:, 0].cpu().numpy() * 17.5) - 17.5
            for prob, gt, p_lk, img_vv in zip(probs, ms, plk, vv):
                pred = (prob > T).astype(np.uint8)
                gc = comps(gt) if gt.any() else []
                gt_big += sum(1 for g in gc if g["px"] >= 1000)
                if not pred.any():
                    continue
                pc = [c for c in comps(pred) if c["px"] >= MIN_AREA]
                if not pc:
                    continue
                pred_frac = pred.mean()
                feats = np.array([comp_features(c, prob, img_vv, len(pc),
                                                pred_frac, p_lk) for c in pc])
                scores = 1 / (1 + np.exp(-(((feats - mu) / sd) @ w + b)))
                for s, st in rows_stats.items():
                    kept = [c for c, sc in zip(pc, scores) if sc >= s]
                    st["pred"] += len(kept)
                    used = [False] * len(kept)
                    for g in gc:
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
                            if g["px"] >= 1000:
                                st["big"] += 1
    report = []
    for s, st in rows_stats.items():
        r = {"score": s,
             "object_precision": round(st["matched"] / max(st["pred"], 1), 4),
             "recall_big_1000px": round(st["big"] / max(gt_big, 1), 4),
             "pred_components": st["pred"]}
        report.append(r)
        print(f"score>={s:.1f}: P {r['object_precision']:.3f} "
              f"R(>=10ha) {r['recall_big_1000px']:.3f} preds {r['pred_components']}",
              flush=True)
    (RUN / "report.json").write_text(json.dumps(
        {"baseline_close25": {"P": 0.810, "R": 0.772},
         "baseline_close15": {"P": 0.783, "R": 0.791},
         "baseline_gate_only": {"P": 0.739, "R": 0.812},
         "rows": report}, indent=1))
    print(f"wrote {RUN/'report.json'}")


if __name__ == "__main__":
    (fit if sys.argv[1] == "fit" else evaluate)()
