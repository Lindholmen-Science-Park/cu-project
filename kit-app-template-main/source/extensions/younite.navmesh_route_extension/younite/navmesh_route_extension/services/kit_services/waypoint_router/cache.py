"""Stage scan + module-level ring / waypoint caches."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pxr import UsdGeom

from .config import BRANCH_OFF_RING, ENTRANCE_PREFIX

# Module-level caches; cleared on ``invalidate()``.
_ring: Optional[List[Tuple[str, Tuple[float, float, float]]]] = None
_all_waypoints: Optional[Dict[str, Tuple[float, float, float]]] = None
_entrances: Optional[List[Tuple[str, Tuple[float, float, float]]]] = None


def invalidate() -> None:
    """Clear cached data so the next call rescans the stage."""
    global _ring, _all_waypoints, _entrances
    _ring = None
    _all_waypoints = None
    _entrances = None


def get_ring() -> Optional[List[Tuple[str, Tuple[float, float, float]]]]:
    return _ring


def get_all_waypoints() -> Optional[Dict[str, Tuple[float, float, float]]]:
    return _all_waypoints


def get_entrances() -> Optional[List[Tuple[str, Tuple[float, float, float]]]]:
    return _entrances


def scan_waypoints(stage) -> List[Tuple[str, Tuple[float, float, float]]]:
    """Return ``[(name, (x,y,z)), ...]`` for every ``/World/nav_waypoint_*`` prim."""
    world = stage.GetPrimAtPath("/World")
    if not world or not world.IsValid():
        return []
    results: List[Tuple[str, Tuple[float, float, float]]] = []
    for child in world.GetChildren():
        name = child.GetName()
        if not name.startswith("nav_waypoint_"):
            continue
        xformable = UsdGeom.Xformable(child)
        if not xformable:
            continue
        try:
            xform = xformable.ComputeLocalToWorldTransform(0)
            t = xform.ExtractTranslation()
            results.append((name, (float(t[0]), float(t[1]), float(t[2]))))
        except Exception:
            continue
    return results


def build_caches(stage) -> None:
    """Build the corridor ring, entrance list, and full waypoint lookup."""
    import math

    global _ring, _all_waypoints, _entrances
    if _ring is not None:
        return

    all_wps = scan_waypoints(stage)
    _all_waypoints = {name: pos for name, pos in all_wps}

    _entrances = [(n, p) for n, p in all_wps if n.startswith(ENTRANCE_PREFIX)]
    entrance_names = {n for n, _ in _entrances}

    off_ring = BRANCH_OFF_RING | entrance_names
    ring_wps = [(n, p) for n, p in all_wps if n not in off_ring]

    if len(ring_wps) < 2:
        _ring = ring_wps
        return

    cx = sum(p[0] for _, p in ring_wps) / len(ring_wps)
    cz = sum(p[2] for _, p in ring_wps) / len(ring_wps)

    def angle(wp):
        _, pos = wp
        return math.atan2(pos[2] - cz, pos[0] - cx)

    _ring = sorted(ring_wps, key=angle)
    names = [n for n, _ in _ring]
    off_names = [n for n in _all_waypoints if n in off_ring]
    print(f"[waypoint_router] Ring built: {len(_ring)} corridor waypoints, order: {names}")
    if _entrances:
        print(f"[waypoint_router] Entrance waypoints: {[n for n, _ in _entrances]}")
    if off_names:
        print(f"[waypoint_router] Off-ring waypoints: {off_names}")


def resolve_name(pos: Tuple[float, float, float]) -> str:
    """Best-effort reverse lookup of a position to a waypoint name."""
    if _all_waypoints:
        for wn, wp in _all_waypoints.items():
            if wp == pos:
                return wn
    return f"({pos[0]:.0f},{pos[2]:.0f})"
