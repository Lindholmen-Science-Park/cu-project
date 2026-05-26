"""Polyline remaining-distance math and lightweight measure / arrival emits."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import omni.usd

from younite.messaging_core_extension.message_utils import dispatch_to_events2

from ....scripts.navmesh_shortest_path import resolve_position
from .constants import (
    ARRIVAL_PATH_GUARD_MAX_REMAINING_CM,
    ROUTE_ARRIVAL_THRESHOLD_CM,
)
from .helpers import point_in_world_aabb
from .types import Vec3


def remaining_distance_along_path(
    player_pos: Tuple[float, float, float],
    path_points: List[Tuple[float, float, float]],
) -> Tuple[float, float]:
    """Compute remaining distance (cm) along the polyline plus vertical offset from the projection.

    Returns ``(remaining_cm, vertical_offset_cm)`` where ``vertical_offset_cm`` is the
    absolute difference between the player's Y (up-axis) and the Y of the player's
    horizontally-projected point on the chosen polyline segment. Callers gate arrival
    on this so a user on a different floor level (e.g. corridor below a stair-top seat)
    is not declared "arrived" just because they line up in XZ.
    """
    if len(path_points) < 2:
        return 0.0, 0.0

    px, py, pz = player_pos[0], player_pos[1], player_pos[2]
    best_seg = 0
    best_dist_sq = float("inf")
    best_t = 0.0

    for i in range(len(path_points) - 1):
        ax, az = path_points[i][0], path_points[i][2]
        bx, bz = path_points[i + 1][0], path_points[i + 1][2]
        dx, dz = bx - ax, bz - az
        seg_len_sq = dx * dx + dz * dz
        if seg_len_sq < 1e-12:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / seg_len_sq))
        proj_x = ax + t * dx
        proj_z = az + t * dz
        d_sq = (px - proj_x) ** 2 + (pz - proj_z) ** 2
        if d_sq < best_dist_sq:
            best_dist_sq = d_sq
            best_seg = i
            best_t = t

    a = path_points[best_seg]
    b = path_points[best_seg + 1]
    proj_y = a[1] + best_t * (b[1] - a[1])
    vertical_offset = abs(py - proj_y)

    remaining = 0.0
    seg_len = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5
    remaining += seg_len * (1.0 - best_t)

    for i in range(best_seg + 1, len(path_points) - 1):
        a = path_points[i]
        b = path_points[i + 1]
        remaining += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5

    return remaining, vertical_offset


class RouteInstanceArrivalMixin:
    """Lightweight remaining-distance ticks and AABB arrival."""

    def _emit_lightweight_measure(self) -> bool:
        """Emit a remaining-distance update using the stored path polyline (no NavMesh re-query).

        Returns True if the player has arrived at the destination (route stopped).
        """
        from ..route_measure import DEFAULT_WALK_SPEED_M_PER_S

        if self._cfg.route_id in ("player", "default"):
            return False
        if not self._get_route_measure_enabled():
            return False
        if not self._last_path_points or len(self._last_path_points) < 2:
            return False
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return False
            start_pos = resolve_position(stage, self._cfg.start_ref, use_ground=self._cfg.start_use_ground)
            player_pos = (float(start_pos[0]), float(start_pos[1]), float(start_pos[2]))

            remaining_cm, _vertical_offset_cm = remaining_distance_along_path(
                player_pos, self._last_path_points
            )

            rid = str(self._cfg.route_id)
            path_ok = remaining_cm <= ARRIVAL_PATH_GUARD_MAX_REMAINING_CM
            in_aabb = False
            if self._arrival_aabb_min is not None and self._arrival_aabb_max is not None:
                in_aabb = point_in_world_aabb(
                    player_pos, self._arrival_aabb_min, self._arrival_aabb_max
                )

            if rid == "seat_nav" and not self._auto_move_active:
                if in_aabb and path_ok:
                    print(
                        f"[NAVMESH_ROUTE:{rid}] Arrival AABB hit (remaining_along_path={remaining_cm:.0f} cm), "
                        "auto-move off — manual arrival"
                    )
                    dispatch_to_events2(
                        "navmeshRouteArrival",
                        {"routeId": rid, "manualNearDestination": True},
                    )
                    self.stop(waypoint_error="lightweight_arrival")
                    return True

            if rid == "seat_nav" and self._auto_move_active:
                if remaining_cm < ROUTE_ARRIVAL_THRESHOLD_CM:
                    if not self._seat_proximity_toast_sent:
                        self._seat_proximity_toast_sent = True
                        print(
                            f"[NAVMESH_ROUTE:{rid}] Within threshold ({remaining_cm:.0f} cm), auto-move on — "
                            f"continuing to path end; UI uses measures until autoMoveStatus arrived"
                        )
            elif rid != "seat_nav":
                if in_aabb and path_ok:
                    print(
                        f"[NAVMESH_ROUTE:{rid}] Arrival AABB hit (remaining_along_path={remaining_cm:.0f} cm)"
                    )
                    dispatch_to_events2("navmeshRouteArrival", {"routeId": rid})
                    self.stop(waypoint_error="lightweight_arrival")
                    return True

            remaining_m = remaining_cm / 100.0
            remaining_s = remaining_m / DEFAULT_WALK_SPEED_M_PER_S if DEFAULT_WALK_SPEED_M_PER_S > 0 else 0.0

            measure_payload: Dict[str, Any] = {
                "routeId": self._cfg.route_id,
                "success": True,
                "distanceMetersBase": remaining_m,
                "estimatedTimeSecondsBase": remaining_s,
                "distanceMetersActual": remaining_m,
                "estimatedTimeSecondsActual": remaining_s,
            }
            measure_payload.update(self.navigation_measure_extras())
            dispatch_to_events2("navmeshRouteMeasure", measure_payload)
        except Exception:
            pass
        return False
