"""Dataclasses and type aliases for the shortcut graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

Vec3 = Tuple[float, float, float]


@dataclass
class ShortcutNode:
    """One Xform on the shortcut graph (e.g. an elevator floor)."""

    group_id: str
    node_id: str
    type_: str
    prim_path: str
    label: str
    i18n_key: Optional[str]
    pos: Vec3


@dataclass
class ShortcutGroup:
    """A set of mutually reachable shortcut nodes (one elevator car)."""

    group_id: str
    type_: str
    label: str
    i18n_key: Optional[str]
    traversal_seconds: float
    wait_seconds: float
    edges: object  # "all" | List[Tuple[str, str]]
    nodes: List[ShortcutNode] = field(default_factory=list)
    serves_sections: frozenset = field(default_factory=frozenset)

    def edge_iter(self) -> List[Tuple[str, str]]:
        """Return the ordered list of (a_node_id, b_node_id) edges."""
        if isinstance(self.edges, str) and self.edges == "all":
            ids = [n.node_id for n in self.nodes]
            out: List[Tuple[str, str]] = []
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    out.append((ids[i], ids[j]))
            return out
        if isinstance(self.edges, list):
            return [(str(a), str(b)) for a, b in self.edges]
        return []


@dataclass
class ShortcutHop:
    """One leg of a shortcut plan: start position, hop, then continue."""

    group_id: str
    type_: str
    from_node: ShortcutNode
    to_node: ShortcutNode
    traversal_seconds: float


@dataclass
class ShortcutPlan:
    """A plan that uses one shortcut hop."""

    hop: ShortcutHop
    walk_to_entrance_cm: float
    walk_from_exit_cm: float
    total_cost_cm: float


WalkLenFn = Callable[[Vec3, Vec3], Optional[float]]
