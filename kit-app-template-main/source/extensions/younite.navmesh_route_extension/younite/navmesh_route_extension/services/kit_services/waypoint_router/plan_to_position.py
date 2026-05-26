"""Symmetric A→B corridor routing using ring + entrances (POI / arbitrary targets)."""
from __future__ import annotations

from typing import List, Tuple

import omni.usd

from .cache import build_caches, get_entrances, get_ring, resolve_name
from .config import SKIP_THRESHOLD_CM
from .geom import dist_xz
from .ring_navmesh import nearest_index, pick_endpoint
from .ring_path import ring_path


def plan_route_to_position(
    player_pos: Tuple[float, float, float],
    target_pos: Tuple[float, float, float],
) -> List[Tuple[float, float, float]]:
    """Return via-points for corridor-guided routing to an arbitrary position.

    Unlike ``plan_route`` this does **not** use a section letter or branch
    chains.  Both endpoints are picked symmetrically by ``pick_endpoint``
    (NavMesh-distance entrance vs ring decision), so the route enters AND
    exits the corridor structure through the best available entrance —
    forward (outdoor → POI) and reverse (POI → outdoor) routes are
    handled the same way.

    Used for restrooms, quiet zones, exits, or any non-seat POI that sits
    on the main corridor level.

    Returns an empty list when waypoints are unavailable or the
    skip-entirely shortcut fires (target is closer than the ring entry
    point and neither side needs an entrance).
    """
    ctx = omni.usd.get_context()
    stage = ctx.get_stage() if ctx else None
    if not stage:
        return []

    build_caches(stage)
    ring = get_ring()
    entrances = get_entrances() or []
    if not ring or len(ring) < 2:
        return []

    end_anchor = nearest_index(ring, target_pos)
    start_idx, entrance_in = pick_endpoint(
        ring, entrances, player_pos, end_anchor, label="Start",
    )
    end_idx, entrance_out = pick_endpoint(
        ring, entrances, target_pos, start_idx, label="End",
    )

    if (
        entrance_in is not None
        and entrance_out is not None
        and entrance_in == entrance_out
    ):
        ent_name = resolve_name(entrance_in)
        print(
            f"[waypoint_router] Both ends share entrance '{ent_name}', "
            f"collapsing to single via point"
        )
        return [entrance_in]

    via: List[Tuple[float, float, float]] = []

    if entrance_in is not None:
        via.append(entrance_in)

    if start_idx == end_idx:
        wp_pos = ring[start_idx][1]
        both_entrances = entrance_in is not None and entrance_out is not None
        no_entrance = entrance_in is None and entrance_out is None
        if no_entrance:
            too_close_to_player = dist_xz(player_pos, wp_pos) < SKIP_THRESHOLD_CM
            too_close_to_target = dist_xz(target_pos, wp_pos) < SKIP_THRESHOLD_CM
            if not (too_close_to_player and too_close_to_target):
                via.append(wp_pos)
        elif both_entrances:
            via.append(wp_pos)
        else:
            ent_name = resolve_name(entrance_in if entrance_in is not None else entrance_out)
            print(
                f"[waypoint_router] Shared ring node '{ring[start_idx][0]}' "
                f"is entrance '{ent_name}'s join — dropping to avoid "
                f"entrance→ring→target detour"
            )
    else:
        indices = ring_path(len(ring), start_idx, end_idx)
        start_wp_pos = ring[start_idx][1]
        if entrance_in is not None or dist_xz(player_pos, start_wp_pos) >= SKIP_THRESHOLD_CM:
            via.append(start_wp_pos)
        for idx in indices[:-1]:
            via.append(ring[idx][1])
        end_wp_pos = ring[end_idx][1]
        if entrance_out is not None or dist_xz(target_pos, end_wp_pos) >= SKIP_THRESHOLD_CM:
            via.append(end_wp_pos)

    if entrance_out is not None:
        if not via or via[-1] != entrance_out:
            via.append(entrance_out)

    if via and entrance_in is None and entrance_out is None:
        dist_to_target = dist_xz(player_pos, target_pos)
        dist_to_ring_entry = dist_xz(player_pos, via[0])
        if dist_to_target < dist_to_ring_entry:
            print(
                f"[waypoint_router] Target ({dist_to_target:.0f} cm) closer than "
                f"ring entry ({dist_to_ring_entry:.0f} cm), skipping waypoints"
            )
            return []

    if via:
        names = [resolve_name(v) for v in via]
        print(f"[waypoint_router] Planned POI route via {len(via)} waypoints: {names}")

    return via
