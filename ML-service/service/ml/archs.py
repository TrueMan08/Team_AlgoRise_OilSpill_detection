"""OilTrace — architecture factory (Phase 3: the challenger tournament).

Every model is addressed by a single string, recorded in the run manifest
and checkpoint config, so training, evaluation, and (eventually) serving
all reconstruct the exact network from the checkpoint alone:

    "unet"                      — the incumbent 7.76M from-scratch U-Net
    "smp:<decoder>:<encoder>"   — segmentation_models_pytorch, ImageNet-
                                  pretrained encoder, e.g.
                                  smp:unet:resnet34
                                  smp:unetplusplus:resnet34
                                  smp:deeplabv3plus:resnet34
                                  smp:unet:efficientnet-b3

Rules of the tournament (docs/ROADMAP_ORG_GRADE.md §3, memory:
oiltrace-no-sacred-architecture): challengers fight on the UNCHANGING v1
val set; object-level metrics decide; nothing is sacred but the split,
the seal, and the claim discipline.

SAR input note: encoders are patched to in_channels=2 (smp reuses
pretrained first-conv weights by channel-cycling — standard practice,
measured fine in the literature for SAR fine-tuning).
"""
from __future__ import annotations

import torch.nn as nn

from ml.model import UNet

_SMP_DECODERS = {
    "unet": "Unet",
    "unetplusplus": "UnetPlusPlus",
    "deeplabv3plus": "DeepLabV3Plus",
    "segformer": "Segformer",
}


def build_model(arch: str = "unet", norm_layer: str = "batch",
                encoder_weights: str | None = "imagenet") -> nn.Module:
    if arch == "unet":
        return UNet(norm=norm_layer)
    if arch.startswith("smp:"):
        import segmentation_models_pytorch as smp  # optional heavy dep
        _, decoder, encoder = arch.split(":")
        cls = getattr(smp, _SMP_DECODERS[decoder])
        return cls(encoder_name=encoder, encoder_weights=encoder_weights,
                   in_channels=2, classes=1)
    raise ValueError(f"unknown arch '{arch}'")
