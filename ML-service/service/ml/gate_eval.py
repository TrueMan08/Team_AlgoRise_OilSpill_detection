"""OilTrace — two-stage gating evaluation (validation only).

Combines stage-1 (scene-context classifier, runs/C1_scene) with stage-2
(E5_focal segmentation) and measures whether suppressing detections in
patches the classifier calls "Lookalike" improves OBJECT precision at
acceptable recall cost.

Gating rule swept on validation: drop a predicted component if its patch's
classifier P(Lookalike) >= tau, for tau in the sweep grid. tau=1.01 row =
no gating (the deployed baseline: obj precision 0.471 / recall(>=10ha)
0.667 at t=0.325, area>=250, conf>=0.60).

Run:  .venv/Scripts/python.exe -m ml.gate_eval [classifier.pth] [seg.pth] [threshold]
(defaults: C1 classifier, E5_focal segmenter at the frozen operating point.
With an explicit threshold >= MIN_CONFIDENCE the per-component confidence
filter is inert and is disabled.)
Writes analysis/gate_eval.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from ml.inference import MIN_AREA_PX, MIN_CONFIDENCE, THRESHOLD, load_model
from ml.patch_dataset import PatchDataset
from ml.scene_classifier import SceneNet

TAUS = [1.01, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4]


def load_classifier(path: str, dev, pretrained: bool = True):
    """Build the right stage-1 net from its checkpoint; returns (fn, ck)
    where fn(x_512) -> logits handles any input pooling itself."""
    ck = torch.load(path, map_location=dev, weights_only=False)
    if str(ck.get("arch", "")).endswith("_2ch"):
        from ml.scene_classifier_v2 import build_resnet_2ch
        clf = build_resnet_2ch(
            ck["arch"].removesuffix("_2ch"), pretrained=pretrained).to(dev)
        clf.load_state_dict(ck["model"])
        clf.eval()
        k = 512 // ck.get("pooled", 256)
        return (lambda x: clf(F.avg_pool2d(x, k))), ck
    clf = SceneNet().to(dev)
    clf.load_state_dict(ck["model"])
    clf.eval()
    return clf, ck


def comps(mask):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8)
    return [{"px": int(stats[k, cv2.CC_STAT_AREA]), "mask": lab == k}
            for k in range(1, n)]


def main():
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    seg_path = sys.argv[2] if len(sys.argv) > 2 else "runs/E5_focal/best.pth"
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else THRESHOLD
    min_conf = MIN_CONFIDENCE if threshold < MIN_CONFIDENCE else 0.0
    seg, _ = load_model(Path(seg_path), dev)
    clf_path = sys.argv[1] if len(sys.argv) > 1 else "runs/C1_scene/best.pth"
    clf, ck = load_classifier(clf_path, dev)
    print(f"classifier: {clf_path} (macro-acc {ck.get('macro_acc'):.3f}) · "
          f"seg: {seg_path} @ t={threshold}", flush=True)
    lk_idx = ck["classes"].index("Lookalike")
    ds = PatchDataset(split="val", normalization="N1")

    stats = {t: {"pred": 0, "matched": 0, "gt_det_big": 0} for t in TAUS}
    gt_big = 0
    t0 = time.time()
    with torch.no_grad():
        for i0 in range(0, len(ds), 16):
            xs, ms = [], []
            for i in range(i0, min(i0 + 16, len(ds))):
                img, mask, _ = ds[i]
                xs.append(img)
                ms.append(mask[0].numpy().astype(np.uint8))
            x = torch.stack(xs).to(dev)
            with torch.amp.autocast(dev.type, enabled=dev.type == "cuda"):
                probs = torch.sigmoid(seg(x).float())[:, 0].cpu().numpy()
                p_lk = torch.softmax(clf(x).float(), 1)[:, lk_idx].cpu().numpy()
            for prob, gt, trap in zip(probs, ms, p_lk):
                pred = (prob > threshold).astype(np.uint8)
                pc = []
                if pred.any():
                    for c in comps(pred):
                        if c["px"] < MIN_AREA_PX:
                            continue
                        conf = float(prob[c["mask"]].mean())
                        if conf < min_conf:
                            continue
                        pc.append(c)
                gc = comps(gt) if gt.any() else []
                gt_big += sum(1 for g in gc if g["px"] >= 1000)
                for tau in TAUS:
                    kept = [] if trap >= tau else pc
                    st = stats[tau]
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
                                st["gt_det_big"] += 1

    rows = []
    for tau in TAUS:
        st = stats[tau]
        rows.append({"tau": tau,
                     "object_precision": round(st["matched"] / max(st["pred"], 1), 4),
                     "recall_big_1000px": round(st["gt_det_big"] / max(gt_big, 1), 4),
                     "pred_components": st["pred"]})
        r = rows[-1]
        label = "NO GATE" if tau > 1 else f"tau={tau:.2f}"
        print(f"{label:9s}: obj precision {r['object_precision']:.3f} "
              f"recall(>=10ha) {r['recall_big_1000px']:.3f} "
              f"preds {r['pred_components']}", flush=True)
    Path("analysis/gate_eval.json").write_text(json.dumps(
        {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "seg": seg_path, "clf": clf_path,
         "clf_macro_acc": ck.get("macro_acc"),
         "base_pipeline": {"threshold": threshold, "min_area": MIN_AREA_PX,
                           "min_conf": min_conf},
         "rule": "drop all components in a patch when P(Lookalike) >= tau",
         "rows": rows, "secs": round(time.time() - t0)}, indent=1))
    print(f"wrote analysis/gate_eval.json ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
