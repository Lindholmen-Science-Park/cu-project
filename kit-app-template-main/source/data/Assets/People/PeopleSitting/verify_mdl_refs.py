"""One-shot diagnostic: walk every Shader prim in the seated-crowd
prototypes (and the seated_people.usda / characters/*.usda wrappers)
and report which MDL files they reference, whether each MDL resolves
to a real file on disk, and which referenced MDLs are missing.

Run with the same Python that runs `generate_seated_pointinstancer.py`.
"""

import os
import sys
from collections import defaultdict

from pxr import Sdf, Usd, UsdShade

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BAKED_DIR = os.path.join(SCRIPT_DIR, "baked")
INSTANCES_USDA = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "..", "Instances", "seated_people.usda"))


def collect_mdl_refs(stage):
    """Return list of (shader_prim_path, mdl_asset_path_str, resolved_path)."""
    out = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdShade.Shader):
            continue
        shader = UsdShade.Shader(prim)
        impl = shader.GetImplementationSource()
        if impl != UsdShade.Tokens.sourceAsset:
            continue
        asset = None
        try:
            res = shader.GetSourceAsset("mdl")
            if res:
                asset = res
        except Exception:
            pass
        if asset is None:
            attr = prim.GetAttribute("info:mdl:sourceAsset")
            if attr and attr.HasValue():
                asset = attr.Get()
        if asset is None:
            continue
        raw = asset.path if hasattr(asset, "path") else str(asset)
        resolved = asset.resolvedPath if hasattr(asset, "resolvedPath") else ""
        out.append((str(prim.GetPath()), raw, resolved))
    return out


def collect_all_asset_refs(stage):
    """Return list of (prim_path, attr_name, raw_asset_path) for every Asset
    valued attribute on every prim — covers MDL sourceAsset, texture inputs,
    references, payloads, sublayers."""
    out = []
    for prim in stage.Traverse():
        for attr in prim.GetAttributes():
            tn = attr.GetTypeName()
            if tn != "asset" and tn != "asset[]":
                continue
            if not attr.HasValue():
                continue
            v = attr.Get()
            if v is None:
                continue
            if tn == "asset":
                items = [v]
            else:
                items = list(v)
            for item in items:
                raw = item.path if hasattr(item, "path") else str(item)
                if raw:
                    out.append((str(prim.GetPath()), attr.GetName(), raw))
    return out


def report(file_path):
    print(f"\n=== {os.path.relpath(file_path, SCRIPT_DIR)} ===")
    if not os.path.exists(file_path):
        print(f"  [MISSING FILE]")
        return set(), set()
    stage = Usd.Stage.Open(file_path)
    if stage is None:
        print(f"  [FAILED TO OPEN]")
        return set(), set()
    refs = collect_mdl_refs(stage)
    asset_refs = collect_all_asset_refs(stage)

    abs_paths = []
    for _prim, _attr, raw in asset_refs:
        if raw.startswith(("/", "\\")) or (len(raw) > 2 and raw[1] == ":"):
            abs_paths.append((_prim, _attr, raw))
        elif "://" in raw and not raw.startswith("./") and not raw.startswith("../"):
            abs_paths.append((_prim, _attr, raw))
    if abs_paths:
        from collections import Counter
        ext_count = Counter()
        for p, a, raw in abs_paths:
            ext = os.path.splitext(raw)[1].lower() or "(none)"
            ext_count[ext] += 1
        print(f"  WARNING: {len(abs_paths)} absolute asset path(s) found "
              f"(by ext: {dict(ext_count)}):")
        seen = set()
        for p, a, raw in abs_paths:
            key = (raw, a)
            if key in seen:
                continue
            seen.add(key)
            print(f"    [{a}] {raw}")
    else:
        print(f"  All {len(asset_refs)} asset references are relative.")

    found, missing = set(), set()
    grouped = defaultdict(list)
    for prim, raw, resolved in refs:
        grouped[(raw, resolved)].append(prim)
    for (raw, resolved), prims in sorted(grouped.items()):
        ok = bool(resolved) and os.path.exists(resolved)
        tag = "OK   " if ok else "MISS "
        if ok:
            found.add(os.path.normpath(resolved))
        else:
            missing.add(raw)
        print(f"  [{tag}] {raw}")
        if resolved and resolved != raw:
            print(f"             resolved -> {resolved}")
        print(f"             used by {len(prims)} shader prim(s)")
    return found, missing


def main():
    targets = []
    if os.path.isdir(BAKED_DIR):
        for fn in sorted(os.listdir(BAKED_DIR)):
            if fn.endswith(".usdc"):
                targets.append(os.path.join(BAKED_DIR, fn))
    targets.append(INSTANCES_USDA)

    all_found, all_missing = set(), set()
    for t in targets:
        f, m = report(t)
        all_found |= f
        all_missing |= m

    print("\n================ SUMMARY ================")
    print(f"Distinct MDL files actually referenced and present on disk: "
          f"{len(all_found)}")
    for p in sorted(all_found):
        print(f"  OK   {p}")
    print(f"\nDistinct MDL references that did NOT resolve to a file: "
          f"{len(all_missing)}")
    for p in sorted(all_missing):
        print(f"  MISS {p}")
    return 1 if all_missing else 0


if __name__ == "__main__":
    sys.exit(main())
