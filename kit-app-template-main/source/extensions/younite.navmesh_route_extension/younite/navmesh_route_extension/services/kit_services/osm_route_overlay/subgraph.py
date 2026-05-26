"""Build the in-memory visible-edge subgraph (matches drawn mesh edges)."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from .constants import VISUAL_EDGE_CLASSES
from .parse_edge import parse_osm_edge


def build_visible_subgraph(
    graph: Any, mode: str
) -> Tuple[Dict[str, Tuple[float, float, float]], Dict[str, List[Tuple[str, float]]]]:
    """Return ``(node_pos_local, adjacency)`` for visible-class edges only."""
    nodes = getattr(graph, "_nodes", {}) or {}
    adj = getattr(graph, "_adj", {}) or {}

    node_pos: Dict[str, Tuple[float, float, float]] = {}
    sub_adj: Dict[str, List[Tuple[str, float]]] = {}
    seen: Set[Tuple[str, str]] = set()

    for nid, neighbors in adj.items():
        ac = nodes.get(nid)
        if not ac or len(ac) < 3:
            continue
        for e in neighbors:
            pe = parse_osm_edge(e, mode)
            if pe is None:
                continue
            nb, dist_cm, ecls, _acc = pe
            if ecls not in VISUAL_EDGE_CLASSES:
                continue
            bc = nodes.get(nb)
            if not bc or len(bc) < 3:
                continue
            key = (nid, nb) if nid < nb else (nb, nid)
            if key in seen:
                continue
            seen.add(key)

            if nid not in node_pos:
                node_pos[nid] = (float(ac[0]), float(ac[1]), float(ac[2]))
            if nb not in node_pos:
                node_pos[nb] = (float(bc[0]), float(bc[1]), float(bc[2]))

            d = float(dist_cm)
            sub_adj.setdefault(nid, []).append((nb, d))
            sub_adj.setdefault(nb, []).append((nid, d))

    return node_pos, sub_adj
