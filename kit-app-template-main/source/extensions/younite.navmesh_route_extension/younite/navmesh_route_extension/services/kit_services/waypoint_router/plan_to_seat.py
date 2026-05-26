"""Seat / section routing: ring + optional upper-section branch chains."""
from __future__ import annotations

from typing import List, Optional, Tuple

import omni.usd

from .branch_trim import filter_upper_branch_for_floor, suffix_upper_branch_from_join_pos
from .cache import build_caches, get_all_waypoints, get_entrances, get_ring, resolve_name
from .config import SKIP_THRESHOLD_CM, UPPER_SECTION_BRANCH
from .geom import dist_xz
from .ring_navmesh import pick_endpoint
from .ring_path import ring_path, ring_travel_distance
from .section_exit import exit_index_for_section


def plan_route(
    player_pos: Tuple[float, float, float],
    seat_pos: Tuple[float, float, float],
    section: str,
    *,
    floor_hint_y: Optional[float] = None,
    branch_join_pos: Optional[Tuple[float, float, float]] = None,
) -> List[Tuple[float, float, float]]:
    """
    Return ordered via-point positions for corridor-guided routing to a seat.

    ``section`` is the seat's section letter (e.g. ``"N"``).  For upper-level
    sections the route goes along the corridor ring to the nearest ring
    waypoint to the staircase, then through the branch chain to the section.

    ``floor_hint_y`` (optional, stage units = cm) trims the upper-section
    branch chain to waypoints at or above roughly that elevation — used
    when the player is already partway up the stairs (e.g. after an
    elevator hop) so ``plan_route`` does not send them back down to lower
    landings.

    ``branch_join_pos`` (optional) is the player's world position when
    rejoining the branch after vertical transport (same units).  After any
    floor trim, the branch suffix starts at the chain waypoint closest to
    this position among staircase and intermediate prims.  If the player is
    within ``JOIN_AT_SECTION_ANCHOR_MAX_CM`` (3D, cm) of the section anchor,
    only that anchor is used — otherwise the anchor is ignored for nearest
    picking so it cannot skip corridor nodes like ``OP_2`` / ``OP_3`` when
    it only wins on vertical layout.
    When that first waypoint is not the staircase prim, the main ring segment
    is omitted so the path does not walk the concourse back to the lower
    landing first.

    Returns an empty list when waypoints are unavailable or no matching
    entrance waypoint is found.
    """
    ctx = omni.usd.get_context()
    stage = ctx.get_stage() if ctx else None
    if not stage:
        return []

    build_caches(stage)
    ring = get_ring()
    all_wps = get_all_waypoints()
    entrances = get_entrances() or []
    if not ring or len(ring) < 2 or not all_wps:
        return []

    end_idx = exit_index_for_section(ring, section, all_wps)
    if end_idx is None:
        return []

    start_idx, entrance_pos = pick_endpoint(
        ring, entrances, player_pos, end_idx, label="Start",
    )

    upper = section.upper()
    if upper in UPPER_SECTION_BRANCH:
        staircase_name = UPPER_SECTION_BRANCH[upper][0]
        staircase_pos = all_wps.get(staircase_name)
        if staircase_pos:
            best_end = end_idx
            best_total = (
                ring_travel_distance(ring, start_idx, end_idx)
                + dist_xz(ring[end_idx][1], staircase_pos)
            )
            for offset in (-1, 1):
                alt = (end_idx + offset) % len(ring)
                alt_total = (
                    ring_travel_distance(ring, start_idx, alt)
                    + dist_xz(ring[alt][1], staircase_pos)
                )
                if alt_total < best_total:
                    best_total = alt_total
                    best_end = alt
            if best_end != end_idx:
                print(
                    f"[waypoint_router] Optimised exit: '{ring[best_end][0]}' "
                    f"beats '{ring[end_idx][0]}' for approach from "
                    f"'{ring[start_idx][0]}'"
                )
                end_idx = best_end

    skip_ring = False
    branch_names_final: List[str] = []
    if upper in UPPER_SECTION_BRANCH:
        staircase_name = UPPER_SECTION_BRANCH[upper][0]
        branch_names_final = list(UPPER_SECTION_BRANCH[upper])
        if floor_hint_y is not None:
            branch_names_final = filter_upper_branch_for_floor(
                branch_names_final, all_wps, float(floor_hint_y),
            )
        if branch_join_pos is not None and branch_names_final:
            branch_names_final = suffix_upper_branch_from_join_pos(
                branch_names_final, all_wps, branch_join_pos,
            )
        if (
            branch_join_pos is not None
            and branch_names_final
            and branch_names_final[0] != staircase_name
        ):
            skip_ring = True
            print(
                "[waypoint_router] Mid-branch rejoin after vertical move: "
                f"skipping ring, branch starts at '{branch_names_final[0]}'"
            )

    via: List[Tuple[float, float, float]] = []

    if entrance_pos is not None:
        via.append(entrance_pos)

    if not skip_ring:
        if start_idx == end_idx:
            wp_pos = ring[start_idx][1]
            if dist_xz(player_pos, wp_pos) >= SKIP_THRESHOLD_CM:
                via.append(wp_pos)
        else:
            indices = ring_path(len(ring), start_idx, end_idx)
            start_wp_pos = ring[start_idx][1]
            if dist_xz(player_pos, start_wp_pos) >= SKIP_THRESHOLD_CM:
                via.append(start_wp_pos)
            for idx in indices:
                via.append(ring[idx][1])

    if upper in UPPER_SECTION_BRANCH:
        for wp_name in branch_names_final:
            pos = all_wps.get(wp_name)
            if pos:
                via.append(pos)

    if via and entrance_pos is None:
        dist_to_seat = dist_xz(player_pos, seat_pos)
        dist_to_ring_entry = dist_xz(player_pos, via[0])
        if dist_to_seat < dist_to_ring_entry:
            print(
                f"[waypoint_router] Seat ({dist_to_seat:.0f} cm) closer than "
                f"ring entry ({dist_to_ring_entry:.0f} cm), skipping waypoints"
            )
            return []

    if via:
        names = [resolve_name(v) for v in via]
        print(f"[waypoint_router] Planned route via {len(via)} waypoints: {names}")

    return via
