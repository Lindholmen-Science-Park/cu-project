"""Pure geometry helpers for route polylines (XZ plane)."""

from __future__ import annotations

import math
from typing import List, Tuple


def xz_dist(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dx = a[0] - b[0]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dz * dz)


def projection_is_forward(
    a: Tuple[float, float, float],
    proj: Tuple[float, float, float],
    b: Tuple[float, float, float],
) -> bool:
    """True when ``proj`` lies between ``a`` and ``b`` along XZ (no backtrack)."""
    ax, _, az = a
    px, _, pz = proj
    bx, _, bz = b
    vx = bx - ax
    vz = bz - az
    v_len2 = vx * vx + vz * vz
    if v_len2 < 1.0:
        return False
    t = ((px - ax) * vx + (pz - az) * vz) / v_len2
    return 0.0 <= t <= 1.0


def dedupe_polyline(
    pts: List[Tuple[float, float, float]],
) -> List[Tuple[float, float, float]]:
    """Drop adjacent waypoints within ~1 cm XZ."""
    if not pts:
        return pts
    out: List[Tuple[float, float, float]] = [pts[0]]
    for p in pts[1:]:
        last = out[-1]
        dx = p[0] - last[0]
        dz = p[2] - last[2]
        if dx * dx + dz * dz > 1.0:
            out.append(p)
    return out
