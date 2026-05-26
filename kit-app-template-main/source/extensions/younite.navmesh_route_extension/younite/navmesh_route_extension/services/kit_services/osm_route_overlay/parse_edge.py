"""Parse OSM adjacency edge tuples using the shared graph cost rules."""

from __future__ import annotations

from typing import Any, Optional, Tuple


def parse_osm_edge(e: Any, mode: str) -> Optional[Tuple[Any, float, str, Optional[str]]]:
    """Accept 2-, 3-, or 4-tuple OSM adjacency edges (legacy graphs).

    Returns ``(neighbor_id, dist_cm, edge_class, access)`` or ``None`` if
    the edge is impassable in ``mode`` (via ``OsmGraphService._edge_cost``).
    """
    try:
        from younite.osm_navigation_extension.osm_graph_service import _edge_cost
    except Exception:
        return None
    if len(e) >= 4:
        nb, dist_cm = e[0], float(e[1])
        ecls = e[2] or "residential"
        access = e[3] if e[3] in ("yes", "no", "limited") else None
    elif len(e) == 3:
        nb, dist_cm, ecls = e[0], float(e[1]), (e[2] or "residential")
        access = None
    elif len(e) == 2:
        nb, dist_cm = e[0], float(e[1])
        ecls, access = "residential", None
    else:
        return None
    if _edge_cost(dist_cm, ecls, access, mode) is None:
        return None
    return nb, dist_cm, ecls, access
