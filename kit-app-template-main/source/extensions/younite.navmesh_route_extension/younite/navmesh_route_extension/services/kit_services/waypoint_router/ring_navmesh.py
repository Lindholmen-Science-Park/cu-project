"""Ring index selection using XZ heuristics + NavMesh distance checks."""
from __future__ import annotations

from typing import List, Optional, Tuple

from ....scripts.navmesh_shortest_path import navmesh_path_length_cm

from .config import (
    MAX_VALIDATION_QUERIES,
    SKIP_THRESHOLD_CM,
    START_CANDIDATES,
    WALL_CHECK_RATIO,
)
from .geom import dist_xz
from .ring_path import ring_path, ring_travel_distance


def navmesh_distance(
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
) -> float:
    """Actual NavMesh path distance between two world positions (cm).

    Returns ``float('inf')`` on failure.
    """
    return navmesh_path_length_cm(a, b)


def nearest_index(
    ring: List[Tuple[str, Tuple[float, float, float]]],
    pos: Tuple[float, float, float],
) -> int:
    """Return the index of the nearest waypoint (XZ distance)."""
    best_i = 0
    best_d = float("inf")
    for i, (_, wp_pos) in enumerate(ring):
        d = dist_xz(pos, wp_pos)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def is_behind_ring_candidate(
    anchor_pos: Tuple[float, float, float],
    cand_idx: int,
    other_idx: int,
    ring: List[Tuple[str, Tuple[float, float, float]]],
) -> bool:
    """True if ``anchor_pos`` is geometrically past ``ring[cand_idx]``
    along the shorter-arc toward ``ring[other_idx]``.
    """
    if cand_idx == other_idx:
        return False
    path = ring_path(len(ring), cand_idx, other_idx)
    if not path:
        return False
    next_idx = path[0]
    cand = ring[cand_idx][1]
    nxt = ring[next_idx][1]
    fwd_x = nxt[0] - cand[0]
    fwd_z = nxt[2] - cand[2]
    ax = anchor_pos[0] - cand[0]
    az = anchor_pos[2] - cand[2]
    return (fwd_x * ax + fwd_z * az) > 0.0


def is_past_entrance(
    anchor_pos: Tuple[float, float, float],
    ent_pos: Tuple[float, float, float],
    ring_join_pos: Tuple[float, float, float],
) -> bool:
    """True if ``anchor_pos`` has crossed ``ent_pos`` into the ring area."""
    dx = ring_join_pos[0] - ent_pos[0]
    dz = ring_join_pos[2] - ent_pos[2]
    px = anchor_pos[0] - ent_pos[0]
    pz = anchor_pos[2] - ent_pos[2]
    return (dx * px + dz * pz) > 0.0


def nearest_ring_by_navmesh(
    ring: List[Tuple[str, Tuple[float, float, float]]],
    pos: Tuple[float, float, float],
) -> Tuple[int, float]:
    """Find the ring waypoint with shortest **NavMesh** walk from ``pos``.

    Returns ``(ring_index, navmesh_distance_cm)``.
    """
    n = len(ring)
    scored = sorted(range(n), key=lambda i: dist_xz(pos, ring[i][1]))
    candidates = scored[: min(START_CANDIDATES, n)]

    best_idx = candidates[0]
    best_nm = float("inf")
    for idx in candidates[:MAX_VALIDATION_QUERIES]:
        nm = navmesh_distance(pos, ring[idx][1])
        if nm < best_nm:
            best_nm = nm
            best_idx = idx
    if best_nm < float("inf"):
        print(
            f"[waypoint_router] Ring join from pos: "
            f"'{ring[best_idx][0]}' (NavMesh {best_nm:.0f} cm)"
        )
    return best_idx, best_nm


def best_ring_index(
    ring: List[Tuple[str, Tuple[float, float, float]]],
    anchor_pos: Tuple[float, float, float],
    other_idx: int,
) -> Tuple[int, float]:
    """Pick the cost-optimised ring node near ``anchor_pos`` toward ``other_idx``.

    Returns ``(ring_index, navmesh_approach_distance)``.
    """
    n = len(ring)
    scored = sorted(range(n), key=lambda i: dist_xz(anchor_pos, ring[i][1]))
    candidates = scored[: min(START_CANDIDATES, n)]

    by_cost = sorted(
        candidates,
        key=lambda i: dist_xz(anchor_pos, ring[i][1])
        + ring_travel_distance(ring, i, other_idx),
    )

    forward_cost = [
        i for i in by_cost
        if not is_behind_ring_candidate(anchor_pos, i, other_idx, ring)
    ]
    if forward_cost:
        dropped = [ring[i][0] for i in by_cost if i not in forward_cost]
        if dropped:
            print(
                f"[waypoint_router] Forward bias dropped behind-anchor "
                f"candidates: {dropped}"
            )
        by_cost = forward_cost

    queries = 0
    for idx in by_cost:
        if queries >= MAX_VALIDATION_QUERIES:
            break
        xz = dist_xz(anchor_pos, ring[idx][1])
        nm = navmesh_distance(anchor_pos, ring[idx][1])
        queries += 1
        if xz < SKIP_THRESHOLD_CM or (xz > 0 and nm / xz <= WALL_CHECK_RATIO):
            chosen = ring[idx][0]
            nearest = ring[candidates[0]][0]
            if idx != candidates[0]:
                print(
                    f"[waypoint_router] Ring node '{chosen}' beats nearest "
                    f"'{nearest}' (XZ cost, NavMesh validated)"
                )
            return idx, nm
        print(
            f"[waypoint_router] Skipping '{ring[idx][0]}' — "
            f"NavMesh/XZ ratio {nm / xz:.1f} suggests wall"
        )

    fallback = by_cost[0]
    print(f"[waypoint_router] All candidates behind walls, fallback '{ring[fallback][0]}'")
    return fallback, float("inf")


def pick_endpoint(
    ring: List[Tuple[str, Tuple[float, float, float]]],
    entrances: List[Tuple[str, Tuple[float, float, float]]],
    pos: Tuple[float, float, float],
    other_idx: int,
    *,
    label: str = "Start",
) -> Tuple[int, Optional[Tuple[float, float, float]]]:
    """Returns ``(ring_idx, entrance_pos_or_None)``."""
    if not entrances:
        ring_idx, _ = best_ring_index(ring, pos, other_idx)
        return ring_idx, None

    ring_join_idx, nm_ring = nearest_ring_by_navmesh(ring, pos)

    best_ent_i = 0
    best_ent_nm = float("inf")
    for i, (_, epos) in enumerate(entrances):
        nm = navmesh_distance(pos, epos)
        if nm < best_ent_nm:
            best_ent_nm = nm
            best_ent_i = i
    ent_name, ent_pos = entrances[best_ent_i]

    print(
        f"[waypoint_router] {label}: NavMesh walk — nearest ring "
        f"'{ring[ring_join_idx][0]}': {nm_ring:.0f} cm, "
        f"entrance '{ent_name}': {best_ent_nm:.0f} cm"
    )

    if best_ent_nm < nm_ring:
        ring_from_ent, _ = nearest_ring_by_navmesh(ring, ent_pos)
        if is_past_entrance(pos, ent_pos, ring[ring_from_ent][1]):
            print(
                f"[waypoint_router] {label}: entrance '{ent_name}' is "
                f"behind anchor — skipping, routing via ring instead."
            )
        else:
            print(
                f"[waypoint_router] {label}: using entrance '{ent_name}', "
                f"ring node '{ring[ring_from_ent][0]}'"
            )
            return ring_from_ent, ent_pos

    ring_idx, _ = best_ring_index(ring, pos, other_idx)
    print(
        f"[waypoint_router] {label}: ring closer — using cost-optimised "
        f"node '{ring[ring_idx][0]}'"
    )
    return ring_idx, None
