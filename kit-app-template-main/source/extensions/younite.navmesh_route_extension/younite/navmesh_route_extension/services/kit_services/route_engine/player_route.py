"""Threaded point-and-click player route compute."""

from __future__ import annotations

import asyncio
import functools
from typing import Dict, List, Optional, Tuple

import omni.kit.app as kit_app

from ....scripts.navmesh_shortest_path import draw_path_curve, smooth_path_xz
from ..route_composer import get_route_composer
from ..route_measure import RouteMeasure
from .constants import PLAYER_PATH_CALC_TIMEOUT_SEC
from .types import Vec3


class RouteInstancePlayerMixin:
    """Worker-thread composer path for ``route_id == "player"``."""

    def _player_compute_in_thread(
        self,
        my_gen: int,
        start_pos: Vec3,
        end_pos: Vec3,
        all_costs: Dict[str, float],
        *,
        allow_osm_bridge: bool,
    ) -> Tuple[bool, List[Vec3], Optional[str], Optional[RouteMeasure]]:
        try:
            if my_gen != self._player_calc_gen:
                return False, [], "superseded", None
            composer = get_route_composer()
            composed = composer.compose(
                start_pos,
                end_pos,
                camera_area_costs=all_costs if all_costs else None,
                via_points=None,
                enable_corridor_routing=False,
                apply_navmesh_validated_straighten=True,
                is_stale=lambda: my_gen != self._player_calc_gen,
                allow_osm_bridge=bool(allow_osm_bridge),
            )
            if my_gen != self._player_calc_gen:
                return False, [], "superseded", None
            if composed is None or len(composed.polyline) < 2:
                return False, [], "no walkable route", None
            points = [(float(p[0]), float(p[1]), float(p[2])) for p in composed.polyline]
            if not composed.has_osm:
                points = smooth_path_xz(points)
            self._last_segment_speeds = (
                list(composed.segment_speeds) if composed.segment_speeds else []
            )
            self._last_segment_classes = (
                list(composed.segment_classes) if composed.segment_classes else []
            )
            return True, points, None, None
        except Exception as e:
            return False, [], str(e), None

    def _apply_player_compute_result(
        self,
        ok: bool,
        points: List[Vec3],
        err: Optional[str],
        measure: Optional[RouteMeasure],
    ) -> None:
        if not self._is_active:
            return
        if not ok:
            self._dirty = False
            self._dispatch_waypoints(self._cfg.route_id, False, [], err or "Path calculation failed", measure)
            print(f"[NAVMESH_ROUTE:{self._cfg.route_id}] Initial calc failed: {err}{self._mode_log_tag()}")
            return
        if self._cfg.draw_path and points:
            from pxr import Gf

            pts_gf = [Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in points]
            d_ok, draw_err = draw_path_curve(
                pts_gf,
                path_prim=self._cfg.path_prim,
                curve_width=self._cfg.curve_width,
            )
            if not d_ok:
                print(f"[NAVMESH_ROUTE:{self._cfg.route_id}] Draw failed: {draw_err}")
        self._last_path_points = points
        self._sync_arrival_aabb_from_path()
        self._cache_positions()
        self._dirty = False
        self._dispatch_waypoints(self._cfg.route_id, True, points, None, measure)
        print(
            f"[NAVMESH_ROUTE:{self._cfg.route_id}] Path calculated: {len(points)} waypoints "
            f"(draw={self._cfg.draw_path}){self._mode_log_tag()}"
        )

    async def _do_player_compute_for_gen(self, my_gen: int) -> None:
        """Run pathfind in a thread with a 1s timeout safety cap."""
        if not self._is_active or str(self._cfg.route_id) != "player":
            return
        await kit_app.get_app().next_update_async()
        if not self._is_active or my_gen != self._player_calc_gen:
            return
        merged: Dict[str, float] = {}
        cc = self._get_camera_area_costs() or {}
        sc = self._get_sound_area_costs() or {}
        if cc:
            merged.update(cc)
        if sc:
            merged.update(sc)

        start_t, end_t, err = self._resolve_endpoints()
        if err or start_t is None or end_t is None:
            self._apply_player_compute_result(False, [], err or "endpoint resolve failed", None)
            return

        self._cache_positions()

        allow_osm = True
        if self._get_allow_player_osm_bridge is not None:
            allow_osm = bool(self._get_allow_player_osm_bridge())

        loop = asyncio.get_running_loop()
        thread_call = functools.partial(
            self._player_compute_in_thread,
            my_gen,
            start_t,
            end_t,
            merged,
            allow_osm_bridge=allow_osm,
        )
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, thread_call),
                PLAYER_PATH_CALC_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            if not self._is_active or my_gen != self._player_calc_gen:
                return
            self._apply_player_compute_result(
                False,
                [],
                f"Path calculation timed out ({PLAYER_PATH_CALC_TIMEOUT_SEC}s). Try a nearby walkable spot.",
                None,
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self._is_active or my_gen != self._player_calc_gen:
                return
            self._apply_player_compute_result(False, [], str(e), None)
            return
        if not self._is_active or my_gen != self._player_calc_gen:
            return
        ok, points, err, measure = result
        if err == "superseded":
            return
        self._apply_player_compute_result(ok, points, err, measure)
