"""``ShortcutRouter`` — load config, scan USD, pick best single-hop plan."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .config_io import load_shortcuts_config_dict
from .constants import (
    DEFAULT_WALK_CM_PER_SEC,
    LOG_PREFIX,
    SHORTCUT_SLACK_FRACTION,
)
from .groups import build_shortcut_groups
from .types import (
    ShortcutGroup,
    ShortcutHop,
    ShortcutNode,
    ShortcutPlan,
    Vec3,
    WalkLenFn,
)
from .usd_scan import scan_navshortcut_node_positions
from .vertical_filters import skip_hop_exit_vertical_backtrack


class ShortcutRouter:
    """Loads shortcuts.json + USD positions and answers shortcut queries."""

    def __init__(
        self,
        *,
        config_path: Optional[str] = None,
        walk_cm_per_sec: float = DEFAULT_WALK_CM_PER_SEC,
    ) -> None:
        self._config_path = config_path
        self._walk_cm_per_sec = float(walk_cm_per_sec)
        self._groups: Dict[str, ShortcutGroup] = {}
        self._loaded = False
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def reload(self) -> None:
        """Re-read shortcuts.json + re-scan USD positions on next query."""
        self._loaded = False
        self._groups = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        cfg = load_shortcuts_config_dict(self._config_path)
        if cfg is None:
            self._loaded = True
            return
        positions = scan_navshortcut_node_positions()
        self._groups = build_shortcut_groups(cfg, positions)
        self._loaded = True
        node_count = sum(len(g.nodes) for g in self._groups.values())
        print(
            f"{LOG_PREFIX} Loaded {len(self._groups)} groups / "
            f"{node_count} nodes from shortcuts.json"
        )

    def get_groups(self) -> List[ShortcutGroup]:
        self._ensure_loaded()
        return list(self._groups.values())

    def get_node_by_prim(self, prim_path: str) -> Optional[ShortcutNode]:
        self._ensure_loaded()
        for grp in self._groups.values():
            for n in grp.nodes:
                if n.prim_path == prim_path:
                    return n
        return None

    def get_group(self, group_id: str) -> Optional[ShortcutGroup]:
        self._ensure_loaded()
        return self._groups.get(group_id)

    def find_best_plan(
        self,
        start: Sequence[float],
        end: Sequence[float],
        walk_len_cm: WalkLenFn,
        *,
        prefer_shortcut: bool = False,
        corridor_section: Optional[str] = None,
        baseline_cm: Optional[float] = None,
    ) -> Optional[ShortcutPlan]:
        """Pick the cheapest valid shortcut hop, or ``None`` if walking wins.

        Returns ``None`` when shortcuts are disabled, no groups load, direct
        walking wins in strict mode, no hop passes vertical filters + NavMesh
        legs, or the seat section gate finds no group listing that section in
        ``servesSections``.

        ``prefer_shortcut=False``: baseline cost is direct walk (or
        ``baseline_cm`` when supplied — POI lists pass corridor+stairs
        length). A hop must be strictly cheaper (``SHORTCUT_SLACK_FRACTION``).
        ``prefer_shortcut=True``: any feasible hop wins if vertical filters pass;
        non-seat routes also require exit Y within ``ELEVATOR_EXIT_TO_DEST_MAX_CM``
        of destination (see ``vertical_filters``).

        Single-hop only. Full policy text: ``.cursor/rules/topics/shortcuts.mdc``.
        """
        if not self._enabled:
            return None
        self._ensure_loaded()
        if not self._groups:
            return None

        is_seat_route = bool(
            corridor_section is not None and str(corridor_section).strip()
        )
        section_norm: Optional[str] = None
        allowed_groups: Optional[frozenset] = None
        if is_seat_route:
            section_norm = str(corridor_section).strip().upper()
            allowed_groups = frozenset(
                grp.group_id
                for grp in self._groups.values()
                if section_norm in grp.serves_sections
            )
            if not allowed_groups:
                return None

        s = (float(start[0]), float(start[1]), float(start[2]))
        e = (float(end[0]), float(end[1]), float(end[2]))

        if prefer_shortcut:
            direct_cm = None
        elif baseline_cm is not None:
            direct_cm = float(baseline_cm)
        else:
            direct_cm = walk_len_cm(s, e)

        best: Optional[ShortcutPlan] = None
        if direct_cm is not None:
            best_cost = float(direct_cm) * (1.0 + SHORTCUT_SLACK_FRACTION)
        else:
            best_cost = float("inf")
        min_completed_total: Optional[float] = None
        navmesh_pairs_ok = 0

        candidates: List[
            Tuple[float, ShortcutGroup, ShortcutNode, ShortcutNode, float]
        ] = []
        for grp in self._groups.values():
            if allowed_groups is not None and grp.group_id not in allowed_groups:
                continue
            hop_cost_cm = (
                grp.traversal_seconds + grp.wait_seconds
            ) * self._walk_cm_per_sec
            for a_id, b_id in grp.edge_iter():
                a = self._find_node(grp, a_id)
                b = self._find_node(grp, b_id)
                if a is None or b is None:
                    continue
                for entrance, exit_ in ((a, b), (b, a)):
                    xz_in = self._xz_dist(s, entrance.pos)
                    xz_out = self._xz_dist(exit_.pos, e)
                    y_align = (
                        0.35 * abs(float(entrance.pos[1]) - s[1])
                        + 0.35 * abs(float(exit_.pos[1]) - e[1])
                    )
                    lower_bound = xz_in + xz_out + hop_cost_cm + y_align
                    candidates.append(
                        (lower_bound, grp, entrance, exit_, hop_cost_cm),
                    )

        candidates.sort(key=lambda c: c[0])

        max_full_evals = 14
        evaluated = 0

        for lower_bound, grp, entrance, exit_, hop_cost_cm in candidates:
            if lower_bound >= best_cost:
                break
            if evaluated >= max_full_evals:
                break
            if skip_hop_exit_vertical_backtrack(
                s,
                e,
                exit_.pos,
                prefer_mode=prefer_shortcut,
                apply_landing_y_check=not is_seat_route,
            ):
                continue
            evaluated += 1
            walk_in = walk_len_cm(s, entrance.pos)
            if walk_in is None:
                continue
            walk_out = walk_len_cm(exit_.pos, e)
            if walk_out is None:
                continue
            navmesh_pairs_ok += 1
            total = walk_in + walk_out + hop_cost_cm
            if min_completed_total is None or total < min_completed_total:
                min_completed_total = total
            if total < best_cost:
                best_cost = total
                best = ShortcutPlan(
                    hop=ShortcutHop(
                        group_id=grp.group_id,
                        type_=grp.type_,
                        from_node=entrance,
                        to_node=exit_,
                        traversal_seconds=grp.traversal_seconds,
                    ),
                    walk_to_entrance_cm=walk_in,
                    walk_from_exit_cm=walk_out,
                    total_cost_cm=total,
                )

        if best is not None:
            h = best.hop
            ride_cm = best.total_cost_cm - best.walk_to_entrance_cm - best.walk_from_exit_cm
            dir_s = (
                f"{direct_cm:.0f}"
                if direct_cm is not None
                else "inf(prefer_shortcut)"
            )
            mode = "prefer" if direct_cm is None else "strict_beat"
            print(
                f"{LOG_PREFIX} shortcut wins: "
                f"group={h.group_id} {h.from_node.node_id}->{h.to_node.node_id} "
                f"walk_in={best.walk_to_entrance_cm:.0f} ride_equiv={ride_cm:.0f} "
                f"walk_out={best.walk_from_exit_cm:.0f} "
                f"shortcut_total={best.total_cost_cm:.0f} cm vs direct={dir_s} cm "
                f"({mode})"
            )
        else:
            dir_s = (
                f"{direct_cm:.0f}"
                if direct_cm is not None
                else "None (no direct navmesh / prefer_shortcut)"
            )
            if min_completed_total is not None:
                delta = (
                    min_completed_total - float(direct_cm)
                    if direct_cm is not None
                    else None
                )
                delta_s = f" delta={delta:+.0f} cm" if delta is not None else ""
                print(
                    f"{LOG_PREFIX} no shortcut beats direct: "
                    f"direct_cm={dir_s} best_hop_total={min_completed_total:.0f} cm"
                    f"{delta_s} (navmesh_hop_pairs={navmesh_pairs_ok}, "
                    f"full_evals={evaluated}/{len(candidates)})"
                )
            else:
                print(
                    f"{LOG_PREFIX} no shortcut beats direct: "
                    f"direct_cm={dir_s} — no hop with both legs on navmesh "
                    f"(full_evals={evaluated}/{len(candidates)})"
                )
        return best

    @staticmethod
    def _xz_dist(a: Sequence[float], b: Sequence[float]) -> float:
        dx = float(a[0]) - float(b[0])
        dz = float(a[2]) - float(b[2])
        return (dx * dx + dz * dz) ** 0.5

    @staticmethod
    def _find_node(grp: ShortcutGroup, node_id: str) -> Optional[ShortcutNode]:
        for n in grp.nodes:
            if n.node_id == node_id:
                return n
        return None
