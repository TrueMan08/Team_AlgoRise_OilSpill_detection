"""OilTrace — SAR scene loader (development sequence step 1 + step 3 assertions).

Frozen-spec contract (Handoff §3, research note §04/§06):
- rasterio -> [2, H, W] float32 torch tensor, RAW dB (VV = band 1, VH = band 2).
  No normalization is baked in: N0/N1/N2 stays a train-time ablation choice.
- mask -> [H, W] uint8 tensor, values strictly {0, 1}.
- Alignment assertions (step 3) run on EVERY scene loaded — including Part I/II
  later, where nothing has been verified yet:
    * image is 2048x2048x2 float32 with a real (non-identity) geotransform + CRS
    * mask dims == image dims; mask has NO independent georeferencing
      (identity transform / no CRS — per Zenodo and the measured Part III state),
      which is what makes inheriting the image geotransform legal.

Measured facts this codes against (Part III, pixel-verified 450/450):
- images: 2048x2048, 2 bands, float32, EPSG:4326, ~8.98e-5 deg pixel (~10 m)
- VV range approx -36..+8 dB, VH approx -35..+13 dB; one scene reaches -65 dB
- Oil masks binary {0,1}; Lookalike / No-oil masks all-zero (hard negatives)

Part III files may be used as CODE FIXTURES for this module (testing code is
not tuning); no parameter may ever be selected on them.
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning
import torch
from torch.utils.data import Dataset

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path(os.environ.get("OILTRACE_DATA", _REPO)) / "02_Test_images_and_ground_truth"
CATEGORIES = ("Oil", "Lookalike", "No oil")

EXPECTED_SIZE = 2048
EXPECTED_BANDS = 2


class AlignmentError(AssertionError):
    """A scene violated the loader's structural/georeferencing contract."""


@dataclass(frozen=True)
class ScenePair:
    scene_id: str          # e.g. "00042"
    category: str          # "Oil" | "Lookalike" | "No oil"
    image_path: Path
    mask_path: Path | None  # None is allowed for Part I/II layouts resolved later


def _assert(cond: bool, msg: str, path: Path) -> None:
    if not cond:
        raise AlignmentError(f"{path}: {msg}")


def read_scene(image_path: Path) -> tuple[torch.Tensor, dict]:
    """Read one SAR scene -> ([2,H,W] float32 raw-dB tensor, geo profile dict).

    The profile dict carries what the geometry stage (mask -> polygon -> WGS84)
    needs: crs, transform, width, height.
    """
    image_path = Path(image_path)
    with rasterio.open(image_path) as src:
        _assert(src.count == EXPECTED_BANDS, f"expected {EXPECTED_BANDS} bands, got {src.count}", image_path)
        _assert((src.width, src.height) == (EXPECTED_SIZE, EXPECTED_SIZE),
                f"expected {EXPECTED_SIZE}x{EXPECTED_SIZE}, got {src.width}x{src.height}", image_path)
        _assert(all(d == "float32" for d in src.dtypes), f"expected float32 bands, got {src.dtypes}", image_path)
        # step-3 georeferencing contract: image must be genuinely georeferenced
        _assert(src.crs is not None, "image has no CRS", image_path)
        _assert(not src.transform.is_identity, "image transform is identity (not georeferenced)", image_path)
        data = src.read()  # (2, H, W) float32, VV band 1 -> index 0, VH band 2 -> index 1
        profile = {
            "crs": src.crs,
            "transform": src.transform,
            "width": src.width,
            "height": src.height,
            "bounds": src.bounds,
        }
    _assert(np.isfinite(data).all(), "non-finite pixels in image", image_path)
    return torch.from_numpy(data), profile


def read_mask(mask_path: Path, image_profile: dict | None = None) -> torch.Tensor:
    """Read one ground-truth mask -> [H,W] uint8 tensor, strictly binary.

    If image_profile is given, enforces the step-3 alignment contract against it.
    """
    mask_path = Path(mask_path)
    with warnings.catch_warnings():
        # Expected: masks are NOT independently georeferenced (Zenodo, verified)
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(mask_path) as src:
            _assert(src.count == 1, f"expected 1 band mask, got {src.count}", mask_path)
            _assert(src.transform.is_identity, "mask unexpectedly georeferenced (non-identity transform)", mask_path)
            _assert(src.crs is None, f"mask unexpectedly carries a CRS: {src.crs}", mask_path)
            if image_profile is not None:
                _assert((src.width, src.height) == (image_profile["width"], image_profile["height"]),
                        "mask dims != image dims — geotransform inheritance would be invalid", mask_path)
            data = src.read(1)
    uniq = np.unique(data)
    _assert(np.isin(uniq, (0, 1)).all(), f"mask not binary, values={uniq[:10]}", mask_path)
    return torch.from_numpy(data.astype(np.uint8))


def discover_pairs(root: Path = DEFAULT_ROOT,
                   categories: Sequence[str] = CATEGORIES) -> list[ScenePair]:
    """Pair Images/<cat>/NNNNN.tif with Mask/<cat>/NNNNN.tif by numeric id."""
    root = Path(root)
    pairs: list[ScenePair] = []
    for cat in categories:
        img_dir, mask_dir = root / "Images" / cat, root / "Mask" / cat
        if not img_dir.exists():
            continue
        masks = {p.stem: p for p in mask_dir.glob("*.tif")} if mask_dir.exists() else {}
        for img in sorted(img_dir.glob("*.tif")):
            pairs.append(ScenePair(scene_id=img.stem, category=cat,
                                   image_path=img, mask_path=masks.get(img.stem)))
    return pairs


class SceneDataset(Dataset):
    """Full-scene dataset: ([2,2048,2048] raw dB, [2048,2048] mask, meta dict).

    Every __getitem__ re-runs the alignment assertions — the contract is
    enforced on every scene this project ever touches, not just samples.
    """

    def __init__(self, pairs: Sequence[ScenePair] | None = None, root: Path = DEFAULT_ROOT):
        self.pairs = list(pairs) if pairs is not None else discover_pairs(root)
        if not self.pairs:
            raise FileNotFoundError(f"no scene pairs found under {root}")

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int):
        pair = self.pairs[idx]
        image, profile = read_scene(pair.image_path)
        if pair.mask_path is not None:
            mask = read_mask(pair.mask_path, image_profile=profile)
        else:
            mask = torch.zeros((profile["height"], profile["width"]), dtype=torch.uint8)
        meta = {"scene_id": pair.scene_id, "category": pair.category,
                "path": str(pair.image_path)}
        return image, mask, meta

    def iter_with_profiles(self) -> Iterator[tuple[torch.Tensor, torch.Tensor, dict, dict]]:
        """Like iteration, but also yields the geo profile (geometry stage needs it)."""
        for pair in self.pairs:
            image, profile = read_scene(pair.image_path)
            mask = (read_mask(pair.mask_path, image_profile=profile)
                    if pair.mask_path is not None
                    else torch.zeros((profile["height"], profile["width"]), dtype=torch.uint8))
            meta = {"scene_id": pair.scene_id, "category": pair.category,
                    "path": str(pair.image_path)}
            yield image, mask, meta, profile
