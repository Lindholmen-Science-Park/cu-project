"""Shared state, endpoint resolution, caching, and route lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

import omni.usd

from ....scripts.navmesh_shortest_path import remove_path_curve, resolve_position
from ..route_measure import RouteMeasure
from .constants import (
    ARRIVAL_AABB_HALF_XZ_CM,
    ARRIVAL_AABB_HALF_Y_CM,
    ARRIVAL_SEAT_MANUAL_AABB_HALF_XZ_CM,
    ARRIVAL_SEAT_MANUAL_AABB_HALF_Y_CM,
    LIGHTWEIGHT_MEASURE_INTERVAL_SEC,
)
from .types import RouteConfig, Vec3


class RouteInstanceBase:
    """Per-route state machine base: config, endpoints, caching, async lifecycle."""

    def __init__(
        self,
        *,
        config: RouteConfig,
        get_camera_area_costs: Callable[[], Dict[str, float]],
        get_sound_area_costs: Callable[[], Dict[str, float]],
        get_route_measure_enabled: Callable[[], bool],
        dispatch_waypoints: Callable[
            [str, bool, List[Tuple[float, float, float]], Optional[str], Optional[RouteMeasure]],
            None,
        ],
        get_allow_player_osm_bridge: Optional[Callable[[], bool]] = None,
    ):
        self._cfg = config
        self._get_camera_area_costs = get_camera_area_costs
        self._get_sound_area_costs = get_sound_area_costs
        self._get_route_measure_enabled = get_route_measure_enabled
        self._dispatch_waypoints = dispatch_waypoints
        self._get_allow_player_osm_bridge = get_allow_player_osm_bridge

        self._is_active = False
        self._dirty = True
        self._auto_move_active = False
        self._last_path_points: List[Tuple[float, float, float]] = []
        self._last_segment_speeds: List[float] = []
        self._last_segment_classes: List[str] = []
        self._last_start_pos: Optional[Tuple[float, float, float]] = None
        self._last_end_pos: Optional[Tuple[float, float, float]] = None
        self._initial_task = None
        self._recalculation_task = None
        self._player_calc_gen: int = 0

        self._nav_milestones: List[Dict[str, Any]] = []
        self._nav_total_cm: float = 0.0
        self._nav_guide_public: Optional[Dict[str, Any]] = None
        self._seat_proximity_toast_sent: bool = False
        self._arrival_aabb_min: Optional[Vec3] = None
        self._arrival_aabb_max: Optional[Vec3] = None

    @property
    def route_id(self) -> str:
        return self._cfg.route_id

    def update_config(self, *, cfg: RouteConfig) -> None:
        if cfg.path_prim and cfg.path_prim != self._cfg.path_prim:
            try:
                remove_path_curve(self._cfg.path_prim)
            except Exception:
                pass
        if self._cfg.draw_path and not cfg.draw_path:
            try:
                remove_path_curve(cfg.path_prim)
            except Exception:
                pass
        was_periodic = self._cfg.enable_periodic_recalc
        self._cfg = cfg
        self._dirty = True
        if not was_periodic and cfg.enable_periodic_recalc and self._is_active:
            if self._recalculation_task is None or self._recalculation_task.done():
                self._recalculation_task = asyncio.ensure_future(self._periodic_loop())

    def get_last_path_points(self) -> List[Tuple[float, float, float]]:
        return list(self._last_path_points)

    def get_arrival_aabb_bounds(self) -> Optional[Tuple[Vec3, Vec3]]:
        """Return ``(min_xyz, max_xyz)`` world AABB at route end, or ``None`` if unset."""
        if self._arrival_aabb_min is None or self._arrival_aabb_max is None:
            return None
        return (self._arrival_aabb_min, self._arrival_aabb_max)

    def _clear_arrival_aabb(self) -> None:
        self._arrival_aabb_min = None
        self._arrival_aabb_max = None

    def _sync_arrival_aabb_from_path(self) -> None:
        """Rebuild arrival volume from the last polyline vertex and route kind."""
        pts = self._last_path_points
        if len(pts) < 2:
            self._clear_arrival_aabb()
            return
        ex, ey, ez = float(pts[-1][0]), float(pts[-1][1]), float(pts[-1][2])
        rid = str(self._cfg.route_id)
        seat_manual = rid == "seat_nav" and not self._auto_move_active
        if seat_manual:
            hx = ARRIVAL_SEAT_MANUAL_AABB_HALF_XZ_CM
            hy = ARRIVAL_SEAT_MANUAL_AABB_HALF_Y_CM
            hz = ARRIVAL_SEAT_MANUAL_AABB_HALF_XZ_CM
        else:
            hx = ARRIVAL_AABB_HALF_XZ_CM
            hy = ARRIVAL_AABB_HALF_Y_CM
            hz = ARRIVAL_AABB_HALF_XZ_CM
        self._arrival_aabb_min = (ex - hx, ey - hy, ez - hz)
        self._arrival_aabb_max = (ex + hx, ey + hy, ez + hz)

    def clear_navigation_runtime(self) -> None:
        self._nav_milestones = []
        self._nav_total_cm = 0.0
        self._nav_guide_public = None

    def set_navigation_runtime(self, guide: Dict[str, Any]) -> None:
        self._nav_milestones = list(guide.get("milestones") or [])
        self._nav_total_cm = float(guide.get("totalCm") or 0.0)
        self._nav_guide_public = {
            "destinationKind": guide.get("destinationKind") or "unknown",
            "steps": list(guide.get("steps") or []),
            "totalDistanceMeters": guide.get("totalDistanceMeters"),
        }

    def navigation_measure_extras(self) -> Dict[str, Any]:
        """Live distance/action to next maneuver for navmeshRouteMeasure."""
        if not self._nav_milestones or len(self._last_path_points) < 2:
            return {}
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage() if ctx else None
            if not stage:
                return {}
            start_pos = resolve_position(stage, self._cfg.start_ref, use_ground=self._cfg.start_use_ground)
            player_pos = (float(start_pos[0]), float(start_pos[1]), float(start_pos[2]))
            from ..navigation_guide import next_maneuver_from_player

            nxt = next_maneuver_from_player(player_pos, self._last_path_points, self._nav_milestones)
            if nxt:
                return {
                    "navigationNextMeters": round(float(nxt["meters"]), 1),
                    "navigationNextAction": str(nxt["action"]),
                }
        except Exception:
            pass
        return {}

    @staticmethod
    def _is_prim_path(ref: Any) -> bool:
        return isinstance(ref, str)

    def _resolve_navmesh_override(self) -> Optional[object]:
        """Return the cached ``INavMesh`` handle this route should query, or None."""
        cb = self._cfg.get_navmesh_override
        if cb is None:
            return None
        try:
            return cb()
        except Exception:
            return None

    def _mode_log_tag(self) -> str:
        """Return a short ' mesh=<mode>' suffix for log lines, or '' if unknown."""
        cb = self._cfg.get_navmesh_mode
        if cb is None:
            return ""
        try:
            mode = cb()
        except Exception:
            return ""
        if not mode:
            return ""
        return f" mesh={mode}"

    def _next_player_calc_gen(self) -> int:
        self._player_calc_gen += 1
        return self._player_calc_gen

    def _resolve_endpoints(self) -> Tuple[Optional[Vec3], Optional[Vec3], Optional[str]]:
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage() if ctx else None
            if not stage:
                return None, None, "stage unavailable"
            sp = resolve_position(stage, self._cfg.start_ref, use_ground=self._cfg.start_use_ground)
            ep = resolve_position(stage, self._cfg.end_ref, use_ground=False)
            return (
                (float(sp[0]), float(sp[1]), float(sp[2])),
                (float(ep[0]), float(ep[1]), float(ep[2])),
                None,
            )
        except Exception as exc:
            return None, None, f"endpoint resolve failed: {exc}"

    def _resolve_player_world_pos(self) -> Optional[Vec3]:
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage() if ctx else None
            if not stage:
                return None
            start_pos = resolve_position(
                stage, self._cfg.start_ref, use_ground=self._cfg.start_use_ground
            )
            return (float(start_pos[0]), float(start_pos[1]), float(start_pos[2]))
        except Exception:
            return None

    def _cache_positions(self) -> None:
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return
            start_pos = resolve_position(stage, self._cfg.start_ref, use_ground=self._cfg.start_use_ground)
            end_pos = resolve_position(stage, self._cfg.end_ref, use_ground=False)
            self._last_start_pos = (float(start_pos[0]), float(start_pos[1]), float(start_pos[2]))
            self._last_end_pos = (float(end_pos[0]), float(end_pos[1]), float(end_pos[2]))
        except Exception:
            pass

    def _should_recalculate_positions(self) -> bool:
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return True

            if not self._is_prim_path(self._cfg.start_ref) and not self._is_prim_path(self._cfg.end_ref):
                return False

            start_pos = resolve_position(stage, self._cfg.start_ref, use_ground=self._cfg.start_use_ground)
            end_pos = resolve_position(stage, self._cfg.end_ref, use_ground=False)
            current_start = (float(start_pos[0]), float(start_pos[1]), float(start_pos[2]))
            current_end = (float(end_pos[0]), float(end_pos[1]), float(end_pos[2]))

            if self._last_start_pos is None or self._last_end_pos is None:
                self._last_start_pos = current_start
                self._last_end_pos = current_end
                return True

            def _dist(a, b):
                return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5

            return (
                _dist(current_start, self._last_start_pos) > self._cfg.position_recalc_threshold
                or _dist(current_end, self._last_end_pos) > self._cfg.position_recalc_threshold
            )
        except Exception:
            return True

    @staticmethod
    def _dist_xz(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        dx = a[0] - b[0]
        dz = a[2] - b[2]
        return (dx * dx + dz * dz) ** 0.5

    def _prune_passed_via_points(
        self,
        player_pos: Tuple[float, float, float],
        via_points: List[Tuple[float, float, float]],
        end_pos: Optional[Tuple[float, float, float]] = None,
    ) -> List[Tuple[float, float, float]]:
        from ..waypoint_router import (
            VIA_POINT_REACHED_CM as _SHARED_REACHED_CM,
            prune_passed_via_points as _shared_prune,
        )

        original_count = len(via_points)
        pruned = _shared_prune(
            player_pos,
            list(via_points),
            end_pos,
            reached_threshold_cm=_SHARED_REACHED_CM,
        )
        dropped = original_count - len(pruned)
        if dropped > 0:
            print(
                f"[NAVMESH_ROUTE:{self._cfg.route_id}] "
                f"Pruned {dropped} passed via-points, {len(pruned)} remaining"
            )
        return pruned

    def recalc_now(self) -> None:
        if not self._is_active:
            return
        if self._cfg.route_id == "player":
            self._dispatch_waypoints(self._cfg.route_id, False, [], "recalculating", None)
            g = self._next_player_calc_gen()
            asyncio.ensure_future(self._do_player_compute_for_gen(g))
            return
        ok, points, err, measure = self._compute_path()
        self._dispatch_waypoints(self._cfg.route_id, ok, points, err, measure)

    async def _initial_calc(self) -> None:
        try:
            from ..navmesh_bake_utils import wait_for_navmesh_ready

            if self._resolve_navmesh_override() is None:
                if not await wait_for_navmesh_ready(log_prefix=f"NAVMESH_ROUTE:{self._cfg.route_id}"):
                    print(f"[NAVMESH_ROUTE:{self._cfg.route_id}] Timeout waiting for navmesh bake; attempting anyway...")
            if self._cfg.route_id == "player":
                g = self._next_player_calc_gen()
                await self._do_player_compute_for_gen(g)
                return
            ok, points, err, measure = self._compute_path()
            self._dispatch_waypoints(self._cfg.route_id, ok, points, err, measure)
            if ok:
                print(
                    f"[NAVMESH_ROUTE:{self._cfg.route_id}] Path calculated: {len(points)} waypoints "
                    f"(draw={self._cfg.draw_path}){self._mode_log_tag()}"
                )
            else:
                print(f"[NAVMESH_ROUTE:{self._cfg.route_id}] Initial calc failed: {err}{self._mode_log_tag()}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._dispatch_waypoints(self._cfg.route_id, False, [], str(e), None)

    def _needs_full_recalc(self) -> bool:
        if self._dirty:
            return True
        if self._auto_move_active:
            return False
        if self._should_recalculate_positions():
            return True
        return False

    async def _periodic_loop(self) -> None:
        full_recalc_elapsed = 0.0
        try:
            while self._is_active and self._cfg.enable_periodic_recalc:
                await asyncio.sleep(LIGHTWEIGHT_MEASURE_INTERVAL_SEC)
                if not self._is_active or not self._cfg.enable_periodic_recalc:
                    break

                full_recalc_elapsed += LIGHTWEIGHT_MEASURE_INTERVAL_SEC

                if full_recalc_elapsed >= self._cfg.recalc_interval:
                    full_recalc_elapsed = 0.0
                    if not self._needs_full_recalc():
                        if self._emit_lightweight_measure():
                            break
                        continue
                    if self._cfg.route_id == "player":
                        g = self._next_player_calc_gen()
                        await self._do_player_compute_for_gen(g)
                    else:
                        ok, points, err, measure = self._compute_path()
                        self._dispatch_waypoints(self._cfg.route_id, ok, points, err, measure)
                    continue

                if self._emit_lightweight_measure():
                    break
        except Exception:
            pass

    def start(self) -> None:
        self.stop()
        self._dirty = True
        self._last_path_points = []
        self._last_start_pos = None
        self._last_end_pos = None

        self._is_active = True
        self._initial_task = asyncio.ensure_future(self._initial_calc())
        if self._cfg.enable_periodic_recalc:
            self._recalculation_task = asyncio.ensure_future(self._periodic_loop())

    def stop(self, waypoint_error: Optional[str] = None) -> None:
        was_active = self._is_active
        self._is_active = False
        try:
            if self._initial_task and not self._initial_task.done():
                self._initial_task.cancel()
        except Exception:
            pass
        self._initial_task = None
        try:
            if str(self._cfg.route_id) == "player":
                self._next_player_calc_gen()
        except Exception:
            pass
        try:
            if self._recalculation_task and not self._recalculation_task.done():
                self._recalculation_task.cancel()
        except Exception:
            pass
        self._recalculation_task = None

        try:
            remove_path_curve(self._cfg.path_prim)
        except Exception:
            pass

        self._last_path_points = []
        self._clear_arrival_aabb()
        self._dirty = True
        if was_active:
            err = waypoint_error if waypoint_error is not None else "stopped"
            self._dispatch_waypoints(self._cfg.route_id, False, [], err, None)
