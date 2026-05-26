"""
One-time offline tool: generate fall and winter texture variants
from the tree atlas embedded in VEG_10500_Traed_genericTree.usdz.

Run after pulling Nucleus data (pullnucleus.bat) so the USDZ is available.

Texture layout (4096x4096 RGBA):
  Left half  (x < 2048)  — bark / trunk  (keep untouched)
  Right half (x >= 2048) — leaf branch sprites on transparent bg

Spring → same green as summer but with partial leaf removal (budding)
Fall   → per-block color mix (yellow/orange/green) + partial leaf removal
Winter → zero the alpha on leaf region so leaves disappear

Usage:
    pip install -r requirements.txt
    python generate_seasonal_textures.py
"""

from __future__ import annotations

import os
import sys
import zipfile
import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
NUCLEUS_ASSETS = os.path.join(
    DATA_DIR, "nucleus", "city_tiles", "References", "Assets"
)
USDZ_PATH = os.path.join(NUCLEUS_ASSETS, "VEG_10500_Traed_genericTree.usdz")
OUT_DIR = os.path.join(DATA_DIR, "Assets", "SeasonalTextures")
TEX_NAME_IN_USDZ = "SubUSDs/textures/Maple_Red_Field_Color_dark.png"

SPLIT_X = 2048  # left = bark, right = leaves
FALL_LEAF_REMOVE_FRACTION = 0.25
FALL_LEAF_SEED = 42
BLOCK_SIZE = 64  # spatial grid block size in pixels

FALL_COLOR_GREEN = 0.10
FALL_COLOR_ORANGE = 0.10
FALL_COLOR_YELLOW = 0.80


def extract_texture() -> np.ndarray:
    """Extract the RGBA texture from the USDZ archive."""
    if not os.path.isfile(USDZ_PATH):
        print(f"ERROR: USDZ not found at {USDZ_PATH}")
        print("       Run pullnucleus.bat first to fetch Nucleus data.")
        sys.exit(1)
    with zipfile.ZipFile(USDZ_PATH, "r") as z:
        with z.open(TEX_NAME_IN_USDZ) as f:
            img = Image.open(f)
            img.load()
    return np.array(img.convert("RGBA"))


def _apply_yellow(r, g, b):
    """Golden yellow — warm, high green retention."""
    return (
        np.clip(r * 1.15 + 30, 0, 255),
        np.clip(g * 0.90 + 5, 0, 255),
        np.clip(b * 0.25, 0, 255),
    )

def _apply_orange(r, g, b):
    """Deep orange/red — the original autumn palette."""
    return (
        np.clip(r * 1.25 + 20, 0, 255),
        np.clip(g * 0.55 - 5, 0, 255),
        np.clip(b * 0.30, 0, 255),
    )


SPRING_LEAF_REMOVE_FRACTION = FALL_LEAF_REMOVE_FRACTION
SPRING_LEAF_SEED = 7


def _leaf_block_coords(right: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return (y0, y1, x0, x1) for every BLOCK_SIZE block with opaque pixels."""
    h, w = right.shape[:2]
    coords = []
    for br in range((h + BLOCK_SIZE - 1) // BLOCK_SIZE):
        for bc in range((w + BLOCK_SIZE - 1) // BLOCK_SIZE):
            y0, y1 = br * BLOCK_SIZE, min((br + 1) * BLOCK_SIZE, h)
            x0, x1 = bc * BLOCK_SIZE, min((bc + 1) * BLOCK_SIZE, w)
            if np.any(right[y0:y1, x0:x1, 3] > 0):
                coords.append((y0, y1, x0, x1))
    return coords


def make_spring(arr: np.ndarray) -> np.ndarray:
    """Original green colour with the same block-grid leaf removal as fall."""
    out = arr.copy()
    right = out[:, SPLIT_X:]

    rng = np.random.default_rng(SPRING_LEAF_SEED)
    coords = _leaf_block_coords(right)
    rolls = rng.random(len(coords))

    removed = 0
    for i, (y0, y1, x0, x1) in enumerate(coords):
        if rolls[i] < SPRING_LEAF_REMOVE_FRACTION:
            blk = right[y0:y1, x0:x1]
            blk[blk[:, :, 3] > 0] = 0
            removed += 1

    print(f"  Blocks: {len(coords)} with leaves — {removed} removed")

    transparent = right[:, :, 3] == 0
    right[transparent, :3] = 0

    out[:, SPLIT_X:] = right
    return out


def make_fall(arr: np.ndarray) -> np.ndarray:
    """
    Block-grid autumn treatment: divide the leaf region into BLOCK_SIZE x BLOCK_SIZE
    blocks. Each block with opaque pixels is randomly assigned a role:
    remove (25%), green (7.5%), orange (7.5%), or yellow (60%).
    """
    out = arr.copy()
    right = out[:, SPLIT_X:]
    h, w = right.shape[:2]

    rgb_f = right[:, :, :3].astype(np.float32)
    r, g, b = rgb_f[:, :, 0], rgb_f[:, :, 1], rgb_f[:, :, 2]
    yr, yg, yb = _apply_yellow(r, g, b)
    orr, og, ob = _apply_orange(r, g, b)

    rng = np.random.default_rng(FALL_LEAF_SEED)
    block_coords = _leaf_block_coords(right)
    leaf_blocks = len(block_coords)

    stats = {'remove': 0, 'green': 0, 'orange': 0, 'yellow': 0}

    rolls = rng.random(leaf_blocks)
    remove_thresh = FALL_LEAF_REMOVE_FRACTION
    keep_frac = 1.0 - FALL_LEAF_REMOVE_FRACTION
    green_thresh = remove_thresh + keep_frac * FALL_COLOR_GREEN
    orange_thresh = green_thresh + keep_frac * FALL_COLOR_ORANGE

    for i, (y0, y1, x0, x1) in enumerate(block_coords):
        roll = rolls[i]
        if roll < remove_thresh:
            role = 'remove'
        elif roll < green_thresh:
            role = 'green'
        elif roll < orange_thresh:
            role = 'orange'
        else:
            role = 'yellow'
        stats[role] += 1

        blk = right[y0:y1, x0:x1]
        opaque = blk[:, :, 3] > 0

        if role == 'remove':
            blk[opaque] = 0
        elif role == 'yellow':
            blk[opaque, 0] = yr[y0:y1, x0:x1][opaque].astype(np.uint8)
            blk[opaque, 1] = yg[y0:y1, x0:x1][opaque].astype(np.uint8)
            blk[opaque, 2] = yb[y0:y1, x0:x1][opaque].astype(np.uint8)
        elif role == 'orange':
            blk[opaque, 0] = orr[y0:y1, x0:x1][opaque].astype(np.uint8)
            blk[opaque, 1] = og[y0:y1, x0:x1][opaque].astype(np.uint8)
            blk[opaque, 2] = ob[y0:y1, x0:x1][opaque].astype(np.uint8)

    print(f"  Blocks: {leaf_blocks} with leaves — {stats['remove']} removed, "
          f"{stats['green']} green, {stats['yellow']} yellow, {stats['orange']} orange")

    transparent = right[:, :, 3] == 0
    right[transparent, :3] = 0

    out[:, SPLIT_X:] = right
    return out


FROST_COLOR = np.array([160, 170, 185], dtype=np.float32)
FROST_BLEND = 0.08
FROST_BRIGHTEN = 0.50

BRANCH_FROST_COLOR = np.array([230, 235, 245], dtype=np.float32)
BRANCH_FROST_BLEND = 0.50
BRANCH_FROST_BRIGHTEN = 1.20


LEAF_HUE_LOW = 25
LEAF_HUE_HIGH = 95
LEAF_SAT_MIN = 85


def _leaf_mask(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Return a boolean mask of green leaf pixels (True = leaf, False = branch/stem).

    Uses HSV hue + saturation to distinguish green foliage from brown woody stems.
    """
    from PIL import Image as _Img

    hsv = np.array(_Img.fromarray(rgb, "RGB").convert("HSV"))
    h, s = hsv[:, :, 0], hsv[:, :, 1]
    opaque = alpha > 0
    return opaque & (h >= LEAF_HUE_LOW) & (h <= LEAF_HUE_HIGH) & (s >= LEAF_SAT_MIN)


def make_winter(arr: np.ndarray) -> np.ndarray:
    """Frost-tinted bark + bare branches; remove green leaf pixels from right half."""
    out = arr.copy()

    bark = out[:, :SPLIT_X, :3].astype(np.float32)
    bark = bark * FROST_BRIGHTEN
    bark = bark * (1.0 - FROST_BLEND) + FROST_COLOR * FROST_BLEND
    out[:, :SPLIT_X, :3] = np.clip(bark, 0, 255).astype(np.uint8)

    right = out[:, SPLIT_X:]
    leaves = _leaf_mask(right[:, :, :3], right[:, :, 3])
    right[leaves] = 0

    opaque = (right[:, :, 3] > 0).astype(np.float32)
    from PIL import ImageFilter, Image as _Img
    kernel_size = 31
    density = np.array(
        _Img.fromarray((opaque * 255).astype(np.uint8), "L").filter(
            ImageFilter.BoxBlur(kernel_size // 2)
        )
    ).astype(np.float32) / 255.0
    is_bark = (right[:, :, 3] > 0) & (density > 0.7)
    is_branch = (right[:, :, 3] > 0) & ~is_bark

    right_rgb = right[:, :, :3].astype(np.float32)
    right_rgb[is_bark] = (
        right_rgb[is_bark] * FROST_BRIGHTEN * (1.0 - FROST_BLEND)
        + FROST_COLOR * FROST_BLEND
    )
    right_rgb[is_branch] = (
        right_rgb[is_branch] * BRANCH_FROST_BRIGHTEN * (1.0 - BRANCH_FROST_BLEND)
        + BRANCH_FROST_COLOR * BRANCH_FROST_BLEND
    )
    right[:, :, :3] = np.clip(right_rgb, 0, 255).astype(np.uint8)

    transparent = right[:, :, 3] == 0
    right[transparent, :3] = 0

    out[:, SPLIT_X:] = right
    return out


def save(arr: np.ndarray, name: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    Image.fromarray(arr).save(path, optimize=True)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"  Saved {name} ({size_mb:.1f} MB)")
    return path


def main():
    print("Extracting texture from USDZ …")
    original = extract_texture()
    print(f"  Shape: {original.shape}, dtype: {original.dtype}")

    print("Generating spring variant …")
    spring = make_spring(original)
    save(spring, "Maple_Red_Field_Color_dark_spring.png")

    print("Generating fall variant …")
    fall = make_fall(original)
    save(fall, "Maple_Red_Field_Color_dark_fall.png")

    print("Generating winter variant …")
    winter = make_winter(original)
    save(winter, "Maple_Red_Field_Color_dark_winter.png")

    print("Saving original (summer) copy …")
    save(original, "Maple_Red_Field_Color_dark.png")

    print(f"Done. Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
