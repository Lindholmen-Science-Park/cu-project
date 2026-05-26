"""One-shot rewriter for already-baked sitting-character `.usdc` files.

Background: an earlier version of `bake_skinning.py` exported the flattened
stage directly. `Usd.Stage.Flatten` resolves every reference / asset path to
its absolute on-disk location, which means the produced
`baked/char_NN_*_baked.usdc` files contained machine-specific absolute
paths to MDL and texture assets, e.g.

    D:/dev/goteverse_omniverse_study/kit-app-template-main/source/data/
        Assets/People/Materials/MI_cwom0309m4_ANI_Head.mdl

When a teammate pulled the repo into a different drive or directory, those
paths failed to resolve, Hydra fell back to the red error material, and
RTX logged "Unable to find SdrShaderNode" / "MDL not found" warnings.

`bake_skinning.py` now relativizes paths automatically at the end of every
bake (`_relativize_layer_assets`). This script reuses that exact same helper
to fix the *already committed* baked files in place, so we don't have to
re-run the full UsdSkel bake (which needs the source character + animation
USDs all loaded).

Run from this folder:

    python relativize_baked_paths.py

It is idempotent — re-running on already-relativized files is a no-op (no
attribute is touched, no save happens) so it's safe to run after a fresh
clone if anything looks off.

Note: Unreal-style metadata strings such as
`/Game/AXYZAssets/Materials/MI_xxx.MI_xxx` are intentionally left alone
because they are not file paths (the helper only rewrites values that
`os.path.isfile` confirms exist on disk).
"""
import os

from bake_skinning import BAKED_DIR, _relativize_layer_assets


def main() -> None:
    if not os.path.isdir(BAKED_DIR):
        raise SystemExit(f"Baked dir not found: {BAKED_DIR}")

    files = sorted(
        f for f in os.listdir(BAKED_DIR)
        if f.endswith(".usdc")
    )
    if not files:
        raise SystemExit(f"No .usdc files in {BAKED_DIR}")

    print(f"Anchoring asset paths in {len(files)} file(s) under {BAKED_DIR}")
    total = 0
    for name in files:
        full = os.path.join(BAKED_DIR, name)
        n = _relativize_layer_assets(full)
        total += n
        status = "OK (no change)" if n == 0 else f"rewrote {n} attr(s)"
        print(f"  {name}: {status}")
    print(f"\nDone. {total} attribute(s) rewritten across {len(files)} file(s).")


if __name__ == "__main__":
    main()
