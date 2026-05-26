"""Scan corridor waypoints and named spawn Xforms; nearest magnet in XZ."""

from __future__ import annotations

from typing import List, Optional, Tuple

from .. import waypoint_router
from .constants import SPAWN_PREFIX


def iter_waypoints() -> List[Tuple[str, Tuple[float, float, float]]]:
    try:
        import omni.usd

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return []
        return waypoint_router._scan_waypoints(stage)
    except Exception:
        return []


def iter_named_spawn_points() -> List[Tuple[str, Tuple[float, float, float]]]:
    """Scan ``/World`` for ``PlayerSpawnPoint_*`` Xforms (excluding numeric suffixes).

    Walks descendants so nested spawns (e.g. under avatars) still register.
    """
    try:
        import omni.usd
        from pxr import Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return []
        world = stage.GetPrimAtPath("/World")
        if not (world and world.IsValid()):
            return []

        out: List[Tuple[str, Tuple[float, float, float]]] = []
        for prim in Usd.PrimRange(world):
            if not (prim and prim.IsValid()):
                continue
            if not prim.IsA(UsdGeom.Xform):
                continue
            name = prim.GetName()
            if not name.startswith(SPAWN_PREFIX):
                continue
            suffix = name[len(SPAWN_PREFIX) :]
            if suffix.isdigit():
                continue
            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                continue
            try:
                m = xformable.ComputeLocalToWorldTransform(0)
                t = m.ExtractTranslation()
                out.append((name, (float(t[0]), float(t[1]), float(t[2]))))
            except Exception:
                continue
        return out
    except Exception:
        return []


def nearest_magnet_with_xz_dist2(
    pos: Tuple[float, float, float],
) -> Optional[Tuple[str, Tuple[float, float, float], bool, float]]:
    """Nearest magnet by XZ and its squared horizontal distance, or ``None``."""
    best: Optional[Tuple[str, Tuple[float, float, float], bool, float]] = None
    best_d2 = float("inf")

    for name, wp in iter_waypoints():
        dx = wp[0] - pos[0]
        dz = wp[2] - pos[2]
        d2 = dx * dx + dz * dz
        if d2 < best_d2:
            best_d2 = d2
            best = (name, wp, False, d2)

    for name, sp in iter_named_spawn_points():
        dx = sp[0] - pos[0]
        dz = sp[2] - pos[2]
        d2 = dx * dx + dz * dz
        if d2 < best_d2:
            best_d2 = d2
            best = (name, sp, True, d2)

    return best
