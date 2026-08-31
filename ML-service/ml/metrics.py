"""OilTrace — losses and pixel metrics (frozen spec §07/§08).

Loss: BCE + Dice (E0 default). Metrics: micro Dice/IoU/Precision/Recall
accumulated as TP/FP/FN counts over a whole split, so scene size and batch
boundaries don't skew the aggregate.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F


def focal_dice_loss(logits: torch.Tensor, target: torch.Tensor,
                    dice_weight: float = 1.0, gamma: float = 2.0) -> torch.Tensor:
    """Focal BCE + Dice (experiment E5): down-weights easy pixels, up-weights
    confidently-wrong ones - aimed at look-alike blobs predicted as oil with
    high confidence, which plain BCE barely penalizes once averaged."""
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    pt = torch.exp(-bce)               # prob of the true class
    focal = ((1 - pt) ** gamma * bce).mean()
    prob = torch.sigmoid(logits)
    inter = (prob * target).sum(dim=(1, 2, 3))
    denom = prob.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    dice = (2 * inter + 1.0) / (denom + 1.0)
    return focal + dice_weight * (1 - dice).mean()


def bce_dice_loss(logits: torch.Tensor, target: torch.Tensor,
                  dice_weight: float = 1.0,
                  pos_weight: float | None = None) -> torch.Tensor:
    # pos_weight counteracts background dominance (~97% of pixels in the
    # full corpus): without it, three E0 starts collapsed into the
    # all-background basin (max prob 0.015-0.14 after an epoch)
    pw = (torch.tensor(pos_weight, device=logits.device)
          if pos_weight else None)
    bce = F.binary_cross_entropy_with_logits(logits, target, pos_weight=pw)
    prob = torch.sigmoid(logits)
    inter = (prob * target).sum(dim=(1, 2, 3))
    denom = prob.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    dice = (2 * inter + 1.0) / (denom + 1.0)
    return bce + dice_weight * (1 - dice).mean()


class PixelMetrics:
    """Accumulate TP/FP/FN over batches; report micro Dice/IoU/P/R."""

    def __init__(self):
        self.tp = self.fp = self.fn = 0

    def update(self, pred_bin: torch.Tensor, target: torch.Tensor):
        p = pred_bin.bool()
        t = target.bool()
        self.tp += int((p & t).sum())
        self.fp += int((p & ~t).sum())
        self.fn += int((~p & t).sum())

    def compute(self) -> dict:
        tp, fp, fn = self.tp, self.fp, self.fn
        return {
            "dice": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 1.0,
            "iou": tp / (tp + fp + fn) if (tp + fp + fn) else 1.0,
            "precision": tp / (tp + fp) if (tp + fp) else 1.0,
            "recall": tp / (tp + fn) if (tp + fn) else 1.0,
            "tp": tp, "fp": fp, "fn": fn,
        }
