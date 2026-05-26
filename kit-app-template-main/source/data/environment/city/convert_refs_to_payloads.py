"""
Convert CU-DT-8km2.Project.Scene.usd from stacked references to per-tile payloads.

Before: /world/Geometry has 128 stacked references, tiles are `over` children.
After:  /world/Geometry has no references, each tile is a `def Xform` with its own payload.

Run with Kit's Python (needs pxr.Sdf):
    python convert_refs_to_payloads.py
"""
import os
from pxr import Sdf

SCENE_PATH = os.path.join(os.path.dirname(__file__), "CU-DT-8km2.Project.Scene.usd")

layer = Sdf.Layer.FindOrOpen(SCENE_PATH)
if not layer:
    raise RuntimeError(f"Cannot open {SCENE_PATH}")

geom = layer.GetPrimAtPath("/world/Geometry")
if not geom:
    raise RuntimeError("/world/Geometry not found in layer")

refs = geom.referenceList.prependedItems
print(f"Found {len(refs)} stacked references on /world/Geometry")

children = list(geom.nameChildren)
print(f"Found {len(children)} child specs")

converted = 0
for child in children:
    name = child.name  # e.g. "_00000_CU_DT_8km2"
    parts = name.split("_")
    if len(parts) < 2 or not parts[1].isdigit():
        print(f"  SKIP: {name} (not a tile prim)")
        continue

    num = parts[1]  # "00000"
    file_path = f"./{num}_CU-DT-8km2/{num}_CU-DT-8km2.Tile.Scene.usd"
    target_path = Sdf.Path(f"/Geometry/{name}")

    child.specifier = Sdf.SpecifierDef
    child.typeName = "Xform"
    child.payloadList.prependedItems = [Sdf.Payload(file_path, target_path)]
    converted += 1

print(f"Converted {converted} tiles from over to def+payload")

geom.referenceList.ClearEdits()
print("Cleared stacked references on /world/Geometry")

layer.Save()
print(f"Saved: {SCENE_PATH}")
