"""XZ queries against the full OSM graph and the cached visible subgraph."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

from .constants import VISUAL_EDGE_CLASSES
from .parse_edge import parse_osm_edge


def closest_point_on_edge(
    world_x: float,
    world_z: float,
    *,
    graph: Any,
    mode: str,
    ox: float,
    oz: float,
    visible_only: bool = True,
) -> Optional[Tuple[float, float, float, float]]:
    """Nearest point on any walkable segment; returns ``(x,y,z, dist_xz)``."""
    if graph is None:
        return None
    cx = world_x - ox
    cz = world_z - oz

    nodes = getattr(graph, "_nodes", {}) or {}
    adj = getattr(graph, "_adj", {}) or {}

    best_d2 = float("inf")
    best: Optional[Tuple[float, float, float]] = None
    seen: Set[Tuple[str, str]] = set()

    for nid, neighbors in adj.items():
        ac = nodes.get(nid)
        if not ac or len(ac) < 3:
            continue
        ax, ay, az = float(ac[0]), float(ac[1]), float(ac[2])
        for e in neighbors:
            pe = parse_osm_edge(e, mode)
            if pe is None:
                continue
            nb, _dist, ecls, _acc = pe
            if visible_only and ecls not in VISUAL_EDGE_CLASSES:
                continue
            key = (nid, nb) if nid < nb else (nb, nid)
            if key in seen:
                continue
            seen.add(key)
            bc = nodes.get(nb)
            if not bc or len(bc) < 3:
                continue
            bx, by, bz = float(bc[0]), float(bc[1]), float(bc[2])
            dx = bx - ax
            dz = bz - az
            seg_len2 = dx * dx + dz * dz
            if seg_len2 < 1.0:
                continue
            t = ((cx - ax) * dx + (cz - az) * dz) / seg_len2
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            px = ax + t * dx
            pz = az + t * dz
            ex = px - cx
            ez = pz - cz
            d2 = ex * ex + ez * ez
            if d2 < best_d2:
                best_d2 = d2
                py = ay + t * (by - ay)
                best = (px, py, pz)

    if best is None:
        return None
    return (best[0] + ox, best[1], best[2] + oz, math.sqrt(best_d2))


def closest_visible_edge_endpoints(
    world_x: float,
    world_z: float,
    *,
    visible_adj: Dict[str, List[Tuple[str, float]]],
    visible_node_pos: Dict[str, Tuple[float, float, float]],
    ox: float,
    oz: float,
) -> Optional[Tuple[Tuple[float, float, float], float, str, str, float]]:
    """Returns ``(proj_xyz_world, dist_xz_cm, node_a, node_b, t)``."""
    if not visible_adj or not visible_node_pos:
        return None
    cx = world_x - ox
    cz = world_z - oz

    best_d2 = float("inf")
    best: Optional[Tuple[Tuple[float, float, float], str, str, float]] = None
    seen: Set[Tuple[str, str]] = set()

    for nid, neighbors in visible_adj.items():
        ac = visible_node_pos.get(nid)
        if ac is None:
            continue
        ax, ay, az = ac
        for nb, _d in neighbors:
            key = (nid, nb) if nid < nb else (nb, nid)
            if key in seen:
                continue
            seen.add(key)
            bc = visible_node_pos.get(nb)
            if bc is None:
                continue
            bx, by, bz = bc
            dx = bx - ax
            dz = bz - az
            seg_len2 = dx * dx + dz * dz
            if seg_len2 < 1.0:
                continue
            t = ((cx - ax) * dx + (cz - az) * dz) / seg_len2
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            px = ax + t * dx
            pz = az + t * dz
            ex = px - cx
            ez = pz - cz
            d2 = ex * ex + ez * ez
            if d2 < best_d2:
                best_d2 = d2
                py = ay + t * (by - ay)
                best = ((px + ox, py, pz + oz), nid, nb, t)

    if best is None:
        return None
    proj, na, nb, t = best
    return (proj, math.sqrt(best_d2), na, nb, t)
