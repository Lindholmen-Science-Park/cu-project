"""Upper-section branch chains: floor filter + rejoin suffix."""
from __future__ import annotations

from typing import Dict, List, Tuple

from .config import DEFAULT_BRANCH_FLOOR_TOL_CM, JOIN_AT_SECTION_ANCHOR_MAX_CM
from .geom import dist_3d


def filter_upper_branch_for_floor(
    branch_names: List[str],
    all_wps: Dict[str, Tuple[float, float, float]],
    floor_y: float,
    *,
    tol_cm: float = DEFAULT_BRANCH_FLOOR_TOL_CM,
) -> List[str]:
    """Return branch waypoint names at or above ``floor_y - tol_cm``."""
    out: List[str] = []
    cutoff = float(floor_y) - float(tol_cm)
    for wp_name in branch_names:
        pos = all_wps.get(wp_name)
        if not pos:
            continue
        if float(pos[1]) < cutoff:
            continue
        out.append(wp_name)
    return out


def suffix_upper_branch_from_join_pos(
    branch_names: List[str],
    all_wps: Dict[str, Tuple[float, float, float]],
    join_pos: Tuple[float, float, float],
) -> List[str]:
    """Drop leading branch names so the first kept waypoint matches *join_pos*."""
    if not branch_names:
        return branch_names
    if len(branch_names) <= 1:
        return branch_names
    anchor_name = branch_names[-1]
    anchor_pos = all_wps.get(anchor_name)
    if anchor_pos is not None:
        if dist_3d(join_pos, anchor_pos) <= JOIN_AT_SECTION_ANCHOR_MAX_CM:
            return branch_names[-1:]
    best_i = 0
    best_d2 = float("inf")
    last_exclusive = len(branch_names) - 1
    for i in range(last_exclusive):
        pos = all_wps.get(branch_names[i])
        if not pos:
            continue
        dx = float(join_pos[0]) - float(pos[0])
        dy = float(join_pos[1]) - float(pos[1])
        dz = float(join_pos[2]) - float(pos[2])
        d2 = dx * dx + dy * dy + dz * dz
        if d2 < best_d2:
            best_d2 = d2
            best_i = i
    return branch_names[best_i:]
