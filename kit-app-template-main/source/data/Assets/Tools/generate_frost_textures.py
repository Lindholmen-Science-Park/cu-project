"""
One-time offline tool: generate winter frost / snow-cover texture variants
for city tile terrain and road materials.

Run after pulling Nucleus data (pullnucleus.bat) so the source textures
are available under nucleus/city_tiles/References/Materials/textures/.

Two visual treatments:
  Wet salted — darkened, slightly more saturated, cool-tinted to simulate
               wet salted pavement as seen in Nordic winters (roads,
               concrete, cobblestone …).
  Snow       — heavy desaturation + thick white wash.  Mostly white with
               subtle original detail bleeding through (grass, soil …).

Usage:
    pip install -r requirements.txt
    python generate_frost_textures.py
"""

from __future__ import annotations

import os
import sys
import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
SOURCE_TEX_DIR = os.path.join(
    DATA_DIR, "nucleus", "city_tiles", "References", "Materials", "textures"
)
OUT_DIR = os.path.join(DATA_DIR, "Assets", "SeasonalTextures", "Frost")

# ── wet salted pavement tuning ─────────────────────────────────────
WET_DARKEN = 0.35           # how much to darken (0 = none, 1 = black)
WET_SATURATION_BOOST = 0.20 # extra saturation (wet surfaces look more vivid)
WET_COOL_TINT = np.array([0.93, 0.96, 1.0], dtype=np.float32)  # subtle cold shift

# ── snow cover (natural terrain) tuning ────────────────────────────
SNOW_DESAT = 0.70
SNOW_WHITE_BLEND = 0.65
SNOW_BLUE_TINT = np.array([0.90, 0.93, 1.0], dtype=np.float32)

# ── material categories ───────────────────────────────────────────
FROST_MATERIALS = [
    "Asfalt", "Betong", "Betongplatta", "VG_Kantsten",
    "Smaagatsten", "Storgatsten", "Kullersten", "Natursten", "SF_sten",
    "Sinusplatta", "Trappa", "Mur",
]

SNOW_MATERIALS = [
    "Graes", "Grus", "Sand", "Slaatter", "Skog",
    "aaker", "Jord", "Berg", "Kaerr",
    "Buskage", "Bollplan", "Fallskyddsmatta", "Gummi",
]


def _desaturate(arr: np.ndarray, strength: float) -> np.ndarray:
    """Blend RGB towards luminance-based grey."""
    f = arr.astype(np.float32)
    grey = 0.2989 * f[:, :, 0] + 0.5870 * f[:, :, 1] + 0.1140 * f[:, :, 2]
    grey = np.stack([grey] * 3, axis=-1)
    return f * (1.0 - strength) + grey * strength


def _blend_white(arr_f: np.ndarray, strength: float) -> np.ndarray:
    """Blend towards pure white."""
    return arr_f * (1.0 - strength) + 255.0 * strength


def _apply_tint(arr_f: np.ndarray, tint: np.ndarray) -> np.ndarray:
    """Multiply-blend a per-channel tint (values near 1.0)."""
    return arr_f * tint[np.newaxis, np.newaxis, :]


def _saturate(arr_f: np.ndarray, boost: float) -> np.ndarray:
    """Increase saturation by pulling channels away from luminance."""
    grey = 0.2989 * arr_f[:, :, 0] + 0.5870 * arr_f[:, :, 1] + 0.1140 * arr_f[:, :, 2]
    grey = np.stack([grey] * 3, axis=-1)
    return arr_f + (arr_f - grey) * boost


def make_frost(img: Image.Image) -> Image.Image:
    """Wet salted pavement — darker, more saturated, cool-tinted."""
    arr = np.array(img.convert("RGB")).astype(np.float32)
    arr = arr * (1.0 - WET_DARKEN)
    arr = _saturate(arr, WET_SATURATION_BOOST)
    arr = _apply_tint(arr, WET_COOL_TINT)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def make_snow_cover(img: Image.Image) -> Image.Image:
    """Snow cover — heavy white wash, mostly covering original texture."""
    arr = np.array(img.convert("RGB")).astype(np.float32)
    arr = _desaturate(np.clip(arr, 0, 255).astype(np.uint8), SNOW_DESAT)
    arr = _blend_white(arr, SNOW_WHITE_BLEND)
    arr = _apply_tint(arr, SNOW_BLUE_TINT)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _find_source(name: str) -> str | None:
    """Try .jpg then .png for a material texture name."""
    for ext in (".jpg", ".png"):
        p = os.path.join(SOURCE_TEX_DIR, name + ext)
        if os.path.isfile(p):
            return p
    return None


def _save(img: Image.Image, filename: str) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, filename)
    img.save(path, quality=92, optimize=True)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"    Saved {filename} ({size_mb:.1f} MB)")


def main() -> None:
    if not os.path.isdir(SOURCE_TEX_DIR):
        print(f"ERROR: Source texture directory not found:\n       {SOURCE_TEX_DIR}")
        print("       Run pullnucleus.bat first to fetch Nucleus data.")
        sys.exit(1)

    total = 0
    skipped = 0

    print("Generating frost textures (roads / paved surfaces) …")
    for name in FROST_MATERIALS:
        src = _find_source(name)
        if not src:
            print(f"  SKIP {name} — source texture not found")
            skipped += 1
            continue
        print(f"  Processing {name} …")
        img = Image.open(src)
        ext = os.path.splitext(src)[1]
        out = make_frost(img)
        _save(out, f"{name}_winter_frost{ext}")
        total += 1

    print()
    print("Generating snow-cover textures (natural terrain) …")
    for name in SNOW_MATERIALS:
        src = _find_source(name)
        if not src:
            print(f"  SKIP {name} — source texture not found")
            skipped += 1
            continue
        print(f"  Processing {name} …")
        img = Image.open(src)
        ext = os.path.splitext(src)[1]
        out = make_snow_cover(img)
        _save(out, f"{name}_winter_snow{ext}")
        total += 1

    print()
    print(f"Done. {total} textures generated, {skipped} skipped.")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
