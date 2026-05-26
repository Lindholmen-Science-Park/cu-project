"""Resolve Vec3Ref (prim path or XYZ) to world-space tuples."""

from __future__ import annotations

from typing import Optional, Tuple

from ....scripts.navmesh_shortest_path import resolve_position

from .types import Vec3Ref


def resolve_ref_to_vec3(
    stage,
    ref: Vec3Ref,
    *,
    use_ground: bool,
) -> Optional[Tuple[float, float, float]]:
    """Resolve ``ref`` to (x, y, z) or None if lookup fails / shape invalid."""
    try:
        if isinstance(ref, str):
            gf = resolve_position(stage, ref, use_ground=use_ground)
            return (float(gf[0]), float(gf[1]), float(gf[2]))
        if isinstance(ref, (list, tuple)) and len(ref) >= 3:
            return (float(ref[0]), float(ref[1]), float(ref[2]))
    except Exception:
        return None
    return None
