"""OilTrace — shard-backed patch dataset (consumes stream_to_shards.py output).

Serves 512² (or E1's 256² crops) VV+VH patches from the compressed .npz
shards. Normalization is a CONSTRUCTOR CHOICE (N0/N1/N2 ablation stays open;
shards hold raw dB float16). Augmentation is flips/rot90 only, per the
frozen spec.

    ds = PatchDataset(split="train", normalization="N1", augment=True)
    ds_val = PatchDataset(split="val", normalization="N1")

N0: raw dB unchanged
N1: fixed global affine  (x - N1_CENTER) / N1_SCALE   [candidate default]
N2: per-patch standardization (mean 0 / std 1 per channel)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from torch.utils.data import Dataset

_REPO = Path(__file__).resolve().parents[1]
# OILTRACE_SHARDS lets remote environments (Kaggle: /kaggle/input/<dataset>)
# point at a read-only shard store without touching code.
SHARDS = Path(os.environ.get("OILTRACE_SHARDS", _REPO / "shards"))

# N1 candidate constants: mid/width of the measured Part III dB envelope
# (VV/VH global p1..p99 ≈ −35..0 dB; see analysis/findings.json). CANDIDATE —
# final constants must be recomputed on TRAIN shards only, never Part III.
N1_CENTER = -17.5
N1_SCALE = 17.5


class PatchDataset(Dataset):
    def __init__(self, split: str, parts: Sequence[str] = ("part1", "part2"),
                 normalization: str = "N1", augment: bool = False,
                 patch_size: int = 512, shard_dir: Path = SHARDS, seed: int = 26143):
        assert split in ("train", "val") and normalization in ("N0", "N1", "N2")
        self.norm, self.augment, self.patch_size = normalization, augment, patch_size
        self.rng = np.random.default_rng(seed)
        self.files = sorted(f for p in parts for f in shard_dir.glob(f"{p}_{split}_*.npz"))
        if not self.files:
            raise FileNotFoundError(f"no {split} shards for {parts} under {shard_dir}")
        # index: (file_idx, item_idx); shards stay closed until touched, then cached
        self._counts = []
        for f in self.files:
            with np.load(f) as z:
                self._counts.append(len(z["scene"]))
        self._offsets = np.cumsum([0] + self._counts)
        self._cache: dict[int, dict] = {}
        self._cache_order: list[int] = []
        self._max_cached = 2  # ~2 shards ≈ 4 GB decompressed upper bound

    def __len__(self) -> int:
        return int(self._offsets[-1])

    def _shard(self, fi: int) -> dict:
        if fi not in self._cache:
            with np.load(self.files[fi]) as z:
                self._cache[fi] = {k: z[k] for k in ("images", "masks", "scene")}
            self._cache_order.append(fi)
            if len(self._cache_order) > self._max_cached:
                self._cache.pop(self._cache_order.pop(0), None)
        return self._cache[fi]

    def _normalize(self, x: np.ndarray) -> np.ndarray:
        x = x.astype(np.float32)
        if self.norm == "N0":
            return x
        if self.norm == "N1":
            return (x - N1_CENTER) / N1_SCALE
        mean = x.mean(axis=(1, 2), keepdims=True)
        std = x.std(axis=(1, 2), keepdims=True) + 1e-6
        return (x - mean) / std

    def __getitem__(self, idx: int):
        fi = int(np.searchsorted(self._offsets, idx, side="right") - 1)
        ii = idx - self._offsets[fi]
        shard = self._shard(fi)
        img = shard["images"][ii]     # (2, 512, 512) float16 raw dB
        mask = shard["masks"][ii]     # (512, 512) uint8

        if self.patch_size < img.shape[-1]:  # E1: random 256² crop from stored 512²
            m = img.shape[-1] - self.patch_size
            oy, ox = self.rng.integers(0, m + 1, 2)
            img = img[:, oy:oy + self.patch_size, ox:ox + self.patch_size]
            mask = mask[oy:oy + self.patch_size, ox:ox + self.patch_size]

        if self.augment:  # flips/rot90 only (frozen spec)
            k = int(self.rng.integers(0, 4))
            img, mask = np.rot90(img, k, (1, 2)), np.rot90(mask, k, (0, 1))
            if self.rng.random() < 0.5:
                img, mask = img[:, :, ::-1], mask[:, ::-1]
            img, mask = np.ascontiguousarray(img), np.ascontiguousarray(mask)

        return (torch.from_numpy(self._normalize(img)),
                torch.from_numpy(mask.astype(np.float32))[None],  # (1,H,W) for BCE/Dice
                shard["scene"][ii])

    def oil_flags(self) -> "np.ndarray":
        """Bool per index: does the patch contain any oil? Cached beside the
        shards (one full decompression pass on first call)."""
        import hashlib
        key = hashlib.md5("|".join(f.name for f in self.files).encode()).hexdigest()[:10]
        cache = self.files[0].parent / f"_oil_flags_{key}.npy"
        if cache.exists():
            return np.load(cache)
        flags = np.zeros(len(self), dtype=bool)
        for fi, f in enumerate(self.files):
            with np.load(f) as z:
                flags[self._offsets[fi]:self._offsets[fi + 1]] =                     z["masks"].any(axis=(1, 2))
        try:
            np.save(cache, flags)
        except OSError:  # read-only shard store (Kaggle input) — skip cache
            pass
        return flags

    def summary(self) -> dict:
        pos = 0
        for f in self.files:
            with np.load(f) as z:
                pos += int((z["masks"].any(axis=(1, 2))).sum())
        return {"patches": len(self), "shards": len(self.files),
                "patches_with_oil": pos}
