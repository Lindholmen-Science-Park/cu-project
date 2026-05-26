"""
Pure geometric / polyline helpers for :mod:`route_composer`.

These are stateless functions (no access to the composer's mode
cache or OSM graph) extracted out of ``RouteComposer`` so the class
body stays focused on the compose() flow. Importable on their own
for unit testing.
"""
from __future__ import annotations

from typing import List

from .types import Vec3


def xz_dist2(a: Vec3, b: Vec3) -> float:
    """Squared XZ distance — cheap proxy for "is point A closer than B?"."""
    dx = a[0] - b[0]
    dz = a[2] - b[2]
    return dx * dx + dz * dz


def dedupe_close(
    pts: List[Vec3], min_dist_cm: float = 25.0,
) -> List[Vec3]:
    """Drop consecutive points within ``min_dist_cm`` XZ of each other.

    OSM leg assembly prepends/appends logical endpoints that are
    often near-identical to the first/last OSM node. The auto-mover
    handles tiny segments fine, but a sub-centimetre segment at the
    head of the polyline would waste a time-budget step with
    effectively zero motion; dedup keeps the polyline clean.
    """
    if not pts:
        return pts
    out: List[Vec3] = [pts[0]]
    thresh2 = min_dist_cm * min_dist_cm
    for p in pts[1:]:
        if xz_dist2(p, out[-1]) < thresh2:
            continue
        out.append(p)
    return out


def trim_leading_backtrack(pts: List[Vec3], target: Vec3) -> List[Vec3]:
    """Drop leading points that walk away from ``target``.

    The OSM graph's ``nearest_node`` to a navmesh-edge bridge often
    lands slightly behind the bridge (toward the arena) because the
    bridge is at the navmesh boundary, not on an OSM road. Dijkstra
    then starts by traversing backward a segment or two before
    turning toward the destination, which shows as a "180° hook" on
    the bird-eye overlay.

    Trim strategy: while the second point is further (XZ) from the
    target than the first, drop the first — the path is retreating.
    Once distance starts decreasing monotonically we're on the
    forward portion of the route.
    """
    trimmed = list(pts)
    while len(trimmed) >= 3:
        d0 = xz_dist2(trimmed[0], target)
        d1 = xz_dist2(trimmed[1], target)
        if d1 > d0:
            trimmed.pop(0)
        else:
            break
    return trimmed


def trim_trailing_backtrack(pts: List[Vec3], target: Vec3) -> List[Vec3]:
    """Mirror of :func:`trim_leading_backtrack` for the tail.

    Used on OSM legs in ``osm→navmesh`` flows where the OSM path
    ends near the navmesh bridge but can hook away before reaching
    it — same root cause (bridge not on an OSM node).
    """
    trimmed = list(pts)
    while len(trimmed) >= 3:
        d_last = xz_dist2(trimmed[-1], target)
        d_prev = xz_dist2(trimmed[-2], target)
        if d_prev < d_last:
            trimmed.pop()
        else:
            break
    return trimmed


def is_segment_on_navmesh(
    navmesh,
    a: Vec3,
    b: Vec3,
    *,
    tolerance_cm: float = 50.0,
    sample_spacing_cm: float = 100.0,
) -> bool:
    """Return ``True`` iff every sample on segment ``a→b`` sits on the navmesh.

    Used to discriminate between a valid 2-point straight line
    (open hallway, plaza) and the native pathfinder's fallback
    polyline that just connects unreachable endpoints with a
    direct line. Samples every ``sample_spacing_cm`` along the
    XZ projection of the segment; rejects the segment if any
    sample's nearest navmesh point is more than ``tolerance_cm``
    away in XZ.
    """
    import carb

    dx = b[0] - a[0]
    dz = b[2] - a[2]
    length_xz = (dx * dx + dz * dz) ** 0.5
    # Short segments are never degenerate fallbacks — skip the
    # cost of sampling.
    if length_xz <= sample_spacing_cm:
        return True

    steps = max(2, int(length_xz / sample_spacing_cm))
    tol2 = tolerance_cm * tolerance_cm
    # Skip the endpoints themselves (1..steps-1) — the pathfinder
    # always anchors them on/near navmesh; only mid-segment samples
    # diagnose a wall traversal.
    for i in range(1, steps):
        t = i / float(steps)
        sx = a[0] + dx * t
        sy = a[1] + (b[1] - a[1]) * t
        sz = a[2] + dz * t
        try:
            result = navmesh.query_closest_point(target=carb.Float3(sx, sy, sz))
        except Exception:
            # Bail out — treat as valid rather than crash the route.
            return True
        if result is None:
            return False
        cp, _ = result
        cdx = float(cp.x) - sx
        cdz = float(cp.z) - sz
        if (cdx * cdx + cdz * cdz) > tol2:
            return False
    return True


__all__ = [
    "xz_dist2",
    "dedupe_close",
    "trim_leading_backtrack",
    "trim_trailing_backtrack",
    "is_segment_on_navmesh",
]
