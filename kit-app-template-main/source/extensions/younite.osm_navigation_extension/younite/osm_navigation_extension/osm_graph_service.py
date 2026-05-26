"""Graph-based shortest-path service over a pre-baked OSM way graph.

The service is **mode-aware**: every edge carries a routing **class** (road
classes: ``pedestrian`` / ``steps`` / ``residential`` / ``arterial`` / ``highway``;
rail classes: ``tram`` / ``light_rail`` / ``rail_heavy``) and an optional
``wheelchair`` access flag (``yes`` / ``no`` / ``limited`` / ``None``).
``nearest_node`` and ``shortest_path`` take a ``mode`` argument and use
``MODE_COSTS`` / ``MODE_ACCESS_RULES``.  A ``None`` in either table
hard-excludes the edge for that mode.

Supported modes:
    ``walking``    — default; soft-penalties prefer walkways; **rail
                     edges are excluded.**
    ``wheelchair`` — walking + hard-exclude ``steps`` and ``access='no'``.
    ``car``        — carriageway edges only; **rail excluded.**
    ``tram``       — only ``tram`` and ``light_rail`` ways (for Spårvagn
                     and similar, from ``generate_roads`` railway import).
    ``train``      — ``light_rail`` and ``rail_heavy``; ``tram``-only
                     street trunks excluded.

Legacy graphs without rail classes: rail-only ways were introduced in
``gothenburg_graph.json`` **schema v3** (``includes_railway: true``).
Graphs with only the five road classes still load; rail classes never
appear on their edges, so **tram** / **train** modes have empty
valid-node sets.
"""

import heapq
import json
import math
from collections import deque
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Mode tables
# ---------------------------------------------------------------------------

# Per-class cost multiplier applied to every edge's distance. ``None``
# = hard-exclude that class entirely for the mode.
# Railway edge classes (from ``generate_roads`` / gothenburg_graph.json):
# ``tram``, ``light_rail``, ``rail_heavy`` — not routable for walking/car.
MODE_COSTS: dict[str, dict[str, Optional[float]]] = {
    "walking": {
        "pedestrian":  1.0,
        "steps":       1.2,
        "residential": 3.0,
        "arterial":    10.0,
        "highway":     100.0,
        "tram":        None,
        "light_rail":  None,
        "rail_heavy":  None,
    },
    "wheelchair": {
        "pedestrian":  1.0,
        "steps":       None,  # hard-exclude stairs
        "residential": 3.0,
        "arterial":    10.0,
        "highway":     100.0,
        "tram":        None,
        "light_rail":  None,
        "rail_heavy":  None,
    },
    "car": {
        "pedestrian":  None,  # cars never use walkways
        "steps":       None,
        "residential": 1.5,
        "arterial":    1.0,
        "highway":     0.8,
        "tram":        None,
        "light_rail":  None,
        "rail_heavy":  None,
    },
    # Spårvagn / light-rail vehicle routing on ``railway=tram`` and
    # ``railway=light_rail`` ways only (see transit live overlay).
    "tram": {
        "pedestrian":  None,
        "steps":       None,
        "residential": None,
        "arterial":    None,
        "highway":     None,
        "tram":        1.0,
        "light_rail":  1.0,
        "rail_heavy":  None,
    },
    # Mainline / subway / other heavy rail (optional future use).
    "train": {
        "pedestrian":  None,
        "steps":       None,
        "residential": None,
        "arterial":    None,
        "highway":     None,
        "tram":        None,  # street trams are not inter-city rail
        "light_rail":  1.0,
        "rail_heavy":  1.0,
    },
}

# Per-wheelchair-access multiplier. ``None`` = hard-exclude. The dict
# is keyed by the string from OSM (or ``None`` when the tag is absent).
MODE_ACCESS_RULES: dict[str, dict[Optional[str], Optional[float]]] = {
    "walking": {
        "yes": 1.0, "limited": 1.0, "no": 1.0, None: 1.0,
    },
    "wheelchair": {
        "yes": 0.9,     # slight preference for explicit accessibility
        "limited": 1.0,
        "no": None,     # hard-exclude wheelchair=no edges
        None: 1.0,      # no tag → neutral (most OSM ways are untagged)
    },
    "car": {
        "yes": 1.0, "limited": 1.0, "no": 1.0, None: 1.0,
    },
    "tram": {
        "yes": 1.0, "limited": 1.0, "no": 1.0, None: 1.0,
    },
    "train": {
        "yes": 1.0, "limited": 1.0, "no": 1.0, None: 1.0,
    },
}

DEFAULT_MODE = "walking"


def _edge_cost(
    dist_cm: float,
    edge_class: str,
    access: Optional[str],
    mode: str,
) -> Optional[float]:
    """Return the mode-adjusted edge weight, or ``None`` if the edge is
    hard-excluded under *mode*."""
    class_mult = MODE_COSTS.get(mode, MODE_COSTS[DEFAULT_MODE]).get(edge_class)
    if class_mult is None:
        return None
    access_mult = (
        MODE_ACCESS_RULES.get(mode, MODE_ACCESS_RULES[DEFAULT_MODE]).get(access)
    )
    if access_mult is None:
        return None
    return float(dist_cm) * float(class_mult) * float(access_mult)


class OsmGraphService:
    """Load the pre-built OSM graph and run mode-aware Dijkstra queries."""

    DEFAULT_WALK_SPEED_M_PER_S = 1.3

    def __init__(self):
        # id -> [x, y, z]
        self._nodes: dict[str, list[float]] = {}
        # id -> [[nb, dist_cm, class, access_or_None], ...]
        self._adj: dict[str, list[list]] = {}
        # Per-mode connected-component labels. Each mode gets its own
        # labelling because the mode-filtered sub-graph can differ.
        self._components_by_mode: dict[str, dict[str, int]] = {}
        self._main_component_by_mode: dict[str, Optional[int]] = {}
        # Set of nodes reachable under each mode (cached for fast
        # ``nearest_node`` filtering).
        self._valid_nodes_by_mode: dict[str, set[str]] = {}
        self._loaded = False
        self._legacy_warned = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, graph_path: str | None = None) -> bool:
        """Load *gothenburg_graph.json*. Auto-discovers it when *graph_path* is None."""
        if graph_path is None:
            graph_path = self._discover_graph_path()
        if graph_path is None:
            print("[OSM Graph] Could not locate gothenburg_graph.json")
            return False

        with open(graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._nodes = data["nodes"]
        self._adj = self._normalise_adjacency(data["adjacency"])
        self._loaded = True

        for mode in MODE_COSTS.keys():
            self._index_mode(mode)

        total_edges = sum(len(v) for v in self._adj.values()) // 2
        summary = ", ".join(
            f"{m}={len(self._valid_nodes_by_mode[m])}"
            for m in MODE_COSTS.keys()
        )
        print(
            f"[OSM Graph] Loaded {len(self._nodes)} nodes, {total_edges} edges. "
            f"Mode-valid nodes: {summary}"
        )
        return True

    def _normalise_adjacency(self, raw: dict) -> dict[str, list[list]]:
        """Accept 2-tuple (legacy), 3-tuple, or 4-tuple edges.

        Missing class defaults to ``"residential"`` (the safest pre-mode
        default — the old graph had no car/wheelchair variants anyway).
        Missing access defaults to ``None``.
        """
        normalised: dict[str, list[list]] = {}
        for nid, edges in raw.items():
            out: list[list] = []
            for e in edges:
                nb = e[0]
                dist = float(e[1])
                if len(e) >= 4:
                    cls = e[2] or "residential"
                    access = e[3] if e[3] in ("yes", "no", "limited") else None
                elif len(e) == 3:
                    cls = e[2] or "residential"
                    access = None
                else:
                    cls = "residential"
                    access = None
                    if not self._legacy_warned:
                        print(
                            "[OSM Graph] Legacy 2-tuple adjacency detected — "
                            "regenerate gothenburg_graph.json for mode-aware routing"
                        )
                        self._legacy_warned = True
                out.append([nb, dist, cls, access])
            normalised[nid] = out
        return normalised

    def _index_mode(self, mode: str) -> None:
        """Build valid-node set + connected components for a single mode."""
        valid: set[str] = set()
        for nid, edges in self._adj.items():
            if any(
                _edge_cost(d, c, a, mode) is not None
                for _nb, d, c, a in edges
            ):
                valid.add(nid)
        self._valid_nodes_by_mode[mode] = valid

        # BFS per mode, only across valid edges.
        components: dict[str, int] = {}
        comp_sizes: list[int] = []
        current_id = 0
        for start in valid:
            if start in components:
                continue
            queue = deque([start])
            components[start] = current_id
            size = 0
            while queue:
                u = queue.popleft()
                size += 1
                for nb, d, c, a in self._adj.get(u, []):
                    if nb not in valid or nb in components:
                        continue
                    if _edge_cost(d, c, a, mode) is None:
                        continue
                    components[nb] = current_id
                    queue.append(nb)
            comp_sizes.append(size)
            current_id += 1
        self._components_by_mode[mode] = components
        if comp_sizes:
            self._main_component_by_mode[mode] = max(
                range(len(comp_sizes)), key=lambda i: comp_sizes[i]
            )
        else:
            self._main_component_by_mode[mode] = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def main_component_id(self, mode: str = DEFAULT_MODE) -> Optional[int]:
        return self._main_component_by_mode.get(mode)

    def component_of(self, nid: str, mode: str = DEFAULT_MODE) -> Optional[int]:
        return self._components_by_mode.get(mode, {}).get(nid)

    @classmethod
    def available_modes(cls) -> list[str]:
        return list(MODE_COSTS.keys())

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def nearest_node(
        self,
        x: float,
        z: float,
        *,
        mode: str = DEFAULT_MODE,
        component: Optional[int] = None,
    ) -> Optional[str]:
        """Return the graph node id closest to scene coords *(x, z)*.

        Restricted to nodes that are reachable under *mode* (so a ``car``
        query never snaps onto a footway node, and a ``wheelchair`` query
        never snaps onto a stairs-only node). When *component* is given,
        only nodes in that mode-scoped component are considered.
        """
        if not self._loaded:
            return None
        valid = self._valid_nodes_by_mode.get(mode)
        if valid is None or not valid:
            return None
        components = (
            self._components_by_mode.get(mode) if component is not None else None
        )
        best_id = None
        best_d2 = float("inf")
        for nid in valid:
            if components is not None and components.get(nid) != component:
                continue
            coords = self._nodes.get(nid)
            if coords is None:
                continue
            dx = coords[0] - x
            dz = coords[2] - z
            d2 = dx * dx + dz * dz
            if d2 < best_d2:
                best_d2 = d2
                best_id = nid
        return best_id

    def node_coords(self, nid: str) -> Optional[tuple[float, float, float]]:
        c = self._nodes.get(nid)
        return tuple(c) if c else None

    def edge_class(self, a_id: str, b_id: str) -> Optional[str]:
        """Return the class string of the edge a→b, or ``None`` if missing."""
        for nb, _d, cls, _a in self._adj.get(a_id, []):
            if nb == b_id:
                return cls
        return None

    def shortest_path(
        self,
        start_id: str,
        end_id: str,
        *,
        mode: str = DEFAULT_MODE,
    ) -> tuple[list[str], float]:
        """Mode-aware Dijkstra. Returns *(node_ids, total_distance_cm)*.

        ``total_distance_cm`` is the **true metric distance** (unweighted
        edge lengths summed along the chosen path), not the cost-adjusted
        Dijkstra weight — so walking-time estimates stay correct regardless
        of mode penalties.
        Empty list on failure.
        """
        if not self._loaded or start_id not in self._adj or end_id not in self._adj:
            return [], 0.0
        if mode not in MODE_COSTS:
            mode = DEFAULT_MODE

        dist: dict[str, float] = {start_id: 0.0}
        prev: dict[str, str] = {}
        pq: list = [(0.0, start_id)]

        while pq:
            d, u = heapq.heappop(pq)
            if u == end_id:
                break
            if d > dist.get(u, float("inf")):
                continue
            for nb, edge_dist, cls, access in self._adj.get(u, []):
                cost = _edge_cost(edge_dist, cls, access, mode)
                if cost is None:
                    continue
                nd = d + cost
                if nd < dist.get(nb, float("inf")):
                    dist[nb] = nd
                    prev[nb] = u
                    heapq.heappush(pq, (nd, nb))

        if end_id not in prev and end_id != start_id:
            return [], 0.0

        path: list[str] = []
        cur = end_id
        while cur in prev:
            path.append(cur)
            cur = prev[cur]
        path.append(start_id)
        path.reverse()

        # True metric distance along the chosen path (mode-independent),
        # so walk-time estimates are always accurate.
        total_cm = 0.0
        for a, b in zip(path, path[1:]):
            for nb, ed, _c, _ac in self._adj.get(a, []):
                if nb == b:
                    total_cm += ed
                    break

        return path, total_cm

    def path_to_coords(self, path: list[str]) -> list[tuple[float, float, float]]:
        """Convert a list of node ids to scene coordinates."""
        return [tuple(self._nodes[nid]) for nid in path if nid in self._nodes]

    def path_to_edge_classes(self, path: list[str]) -> list[str]:
        """Return the class string of each edge along *path*.

        ``len(result) == max(0, len(path) - 1)``. Missing edges fall back
        to ``"residential"`` so the list always stays aligned with the
        coord polyline.
        """
        out: list[str] = []
        for a, b in zip(path, path[1:]):
            cls = self.edge_class(a, b)
            out.append(cls or "residential")
        return out

    def estimate_walk_time(self, distance_cm: float) -> float:
        """Return estimated walk time in seconds."""
        distance_m = distance_cm / 100.0
        return distance_m / self.DEFAULT_WALK_SPEED_M_PER_S

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _discover_graph_path() -> Optional[str]:
        probe = Path(__file__).resolve()
        for _ in range(10):
            candidate = probe / "source" / "data" / "osm" / "gothenburg_graph.json"
            if candidate.is_file():
                return str(candidate)
            if probe.name == "kit-app-template-main":
                candidate = probe / "source" / "data" / "osm" / "gothenburg_graph.json"
                if candidate.is_file():
                    return str(candidate)
            parent = probe.parent
            if parent == probe:
                break
            probe = parent
        return None
