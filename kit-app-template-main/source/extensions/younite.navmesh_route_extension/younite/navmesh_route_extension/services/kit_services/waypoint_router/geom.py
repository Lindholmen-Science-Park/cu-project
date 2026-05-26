"""Pure geometry helpers (XZ / 3D distances, via-point pruning)."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from .config import VIA_POINT_REACHED_CM


def dist_xz(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dx = a[0] - b[0]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dz * dz)


def dist_3d(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    dz = float(a[2]) - float(b[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def prune_passed_via_points(
    player_pos: Tuple[float, float, float],
    via_points: List[Tuple[float, float, float]],
    end_pos: Optional[Tuple[float, float, float]] = None,
    *,
    reached_threshold_cm: float = VIA_POINT_REACHED_CM,
) -> List[Tuple[float, float, float]]:
    """Drop via-points the player has already walked past.

    Pure geometric helper shared by every route surface that consumes
    corridor via-points:

    * :class:`RouteInstance` (``route_engine`` package) calls this on every
      ``_compute_path`` so a mid-route recalc does not loop the player
      back through waypoints they already passed.
    * :meth:`RouteComposer._plan_intra_island_via` (``route_composer``)
      calls this on auto-derived corridor via-points so the **bird-eye
      preview** route matches the engine's behaviour (without it the
      preview re-introduces a passed ring waypoint as an "extra arm",
      most visible when the player is already inside the corridor and
      asks for directions to an outdoor map-marker spawn).

    Algorithm: sequential dot-product direction test from the front of
    the via-list. If the player is "ahead" of ``wp[i]`` along the route
    direction (``wp[i] → wp[i+1]`` — or ``wp[-1] → end_pos`` for the
    last waypoint), drop ``wp[i]``. Stops at the first waypoint not yet
    passed. After pruning, also drops the new head waypoint when the
    player is within ``reached_threshold_cm`` of it (XZ).
    """
    if not via_points:
        return []

    n = len(via_points)
    prune_to = 0

    successors = list(via_points[1:])
    if end_pos is not None:
        successors.append(end_pos)

    for i in range(len(successors)):
        wp_curr = via_points[i]
        wp_next = successors[i]
        rdx = wp_next[0] - wp_curr[0]
        rdz = wp_next[2] - wp_curr[2]
        pdx = player_pos[0] - wp_curr[0]
        pdz = player_pos[2] - wp_curr[2]
        dot = rdx * pdx + rdz * pdz
        if dot > 0:
            prune_to = i + 1
        else:
            break

    if prune_to < n:
        if dist_xz(player_pos, via_points[prune_to]) < reached_threshold_cm:
            prune_to += 1

    return via_points[prune_to:]
