"""OilTrace — E0 baseline model: standard U-Net (frozen spec §06).

2 input channels (VV, VH), 1 output logit channel. Base width 32 keeps a
512² batch of 4-8 inside the RTX 4050's 6 GB with AMP. No pretrained
encoder, no attention — E0 is the plain anchor everything else is
measured against.
"""
from __future__ import annotations

import torch
import torch.nn as nn


def _norm(kind: str, ch: int) -> nn.Module:
    # GroupNorm is batch-size independent — the E0_partial run showed
    # small-batch BatchNorm intermittently collapsing val predictions
    return nn.BatchNorm2d(ch) if kind == "batch" else nn.GroupNorm(8, ch)


class DoubleConv(nn.Module):
    def __init__(self, cin: int, cout: int, norm: str = "batch"):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(cin, cout, 3, padding=1, bias=False),
            _norm(norm, cout),
            nn.ReLU(inplace=True),
            nn.Conv2d(cout, cout, 3, padding=1, bias=False),
            _norm(norm, cout),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class UNet(nn.Module):
    def __init__(self, in_ch: int = 2, out_ch: int = 1, base: int = 32,
                 norm: str = "batch"):
        super().__init__()
        c = [base, base * 2, base * 4, base * 8, base * 16]  # 32..512
        self.enc = nn.ModuleList([
            DoubleConv(in_ch, c[0], norm),
            DoubleConv(c[0], c[1], norm),
            DoubleConv(c[1], c[2], norm),
            DoubleConv(c[2], c[3], norm),
        ])
        self.pool = nn.MaxPool2d(2)
        self.bottleneck = DoubleConv(c[3], c[4], norm)
        self.up = nn.ModuleList([
            nn.ConvTranspose2d(c[4], c[3], 2, stride=2),
            nn.ConvTranspose2d(c[3], c[2], 2, stride=2),
            nn.ConvTranspose2d(c[2], c[1], 2, stride=2),
            nn.ConvTranspose2d(c[1], c[0], 2, stride=2),
        ])
        self.dec = nn.ModuleList([
            DoubleConv(c[4], c[3], norm),   # cat(skip c3, up c3)
            DoubleConv(c[3], c[2], norm),
            DoubleConv(c[2], c[1], norm),
            DoubleConv(c[1], c[0], norm),
        ])
        self.head = nn.Conv2d(c[0], out_ch, 1)

    def forward(self, x):
        skips = []
        for enc in self.enc:
            x = enc(x)
            skips.append(x)
            x = self.pool(x)
        x = self.bottleneck(x)
        for up, dec, skip in zip(self.up, self.dec, reversed(skips)):
            x = up(x)
            x = dec(torch.cat([skip, x], dim=1))
        return self.head(x)  # raw logits (loss applies sigmoid)


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters() if p.requires_grad)
