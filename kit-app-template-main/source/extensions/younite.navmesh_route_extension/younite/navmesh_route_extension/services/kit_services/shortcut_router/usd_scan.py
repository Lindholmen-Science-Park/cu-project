"""USD stage scan for /World/NavShortcuts node world positions."""
from __future__ import annotations

from typing import Dict, List

from .constants import LOG_PREFIX
from .types import Vec3


def scan_navshortcut_node_positions() -> Dict[str, Vec3]:
    """Return {prim_path: world_xyz_cm} for every leaf Xform under /World/NavShortcuts."""
    positions: Dict[str, Vec3] = {}
    try:
        import omni.usd
        from pxr import Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            print(f"{LOG_PREFIX} USD scan: no stage")
            return positions
        root = stage.GetPrimAtPath("/World/NavShortcuts")
        if not root or not root.IsValid():
            print(f"{LOG_PREFIX} USD scan: /World/NavShortcuts not in stage")
            return positions
        groups_seen: List[str] = []
        for prim in Usd.PrimRange(root):
            if not prim.IsValid() or prim == root:
                continue
            if prim.GetParent() == root:
                groups_seen.append(prim.GetName())
            if not prim.IsA(UsdGeom.Xformable):
                continue
            children = [c for c in prim.GetChildren() if c.IsA(UsdGeom.Xformable)]
            if children:
                continue
            xf = UsdGeom.Xformable(prim)
            try:
                m = xf.ComputeLocalToWorldTransform(0)
                t = m.ExtractTranslation()
                positions[prim.GetPath().pathString] = (
                    float(t[0]),
                    float(t[1]),
                    float(t[2]),
                )
            except Exception as exc:
                print(f"{LOG_PREFIX} xform read failed for {prim.GetPath()}: {exc}")
        print(
            f"{LOG_PREFIX} USD scan: groups={groups_seen} "
            f"node_paths={list(positions.keys())}"
        )
    except Exception as exc:
        print(f"{LOG_PREFIX} USD scan failed: {exc}")
    return positions
