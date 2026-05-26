"""
NavMesh route service — multi-route manager, cost areas, event dispatch.

Manages multiple RouteInstance objects keyed by route_id. Route calculation
and lifecycle logic lives in the ``route_engine`` package; baking utilities live in
navmesh_bake_utils.py.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from ..navmesh_bake_utils import (
    wait_for_navmesh_ready,
    change_agent_settings_and_rebake as _change_agent_settings_and_rebake,
    rebake_navmesh as _rebake_navmesh,
)
from ..route_engine import RouteConfig, RouteInstance, _safe_prim_name
from ..route_measure import (
    RouteMeasure,
    compute_routes_to_exits as compute_routes_to_exits_impl,
    DEFAULT_WALK_SPEED_M_PER_S,
)
from younite.messaging_core_extension.message_utils import dispatch_to_events2

from .constants import DEFAULT_CAMERA_AREA_COSTS, SHORTCUT_ROUTE_IDS
from .refs import normalize_vec3_ref
from .waypoint_dispatch import dispatch_navmesh_route_waypoints


class NavMeshRouteService:
    """Manager for multiple NavMesh routes (routeId keyed)."""

    def __init__(self):
        self._routes: Dict[str, RouteInstance] = {}
        self._camera_area_costs: Dict[str, float] = dict(DEFAULT_CAMERA_AREA_COSTS)
        self._sound_area_costs: Dict[str, float] = {}
        self._route_measure_enabled: bool = True
        self._crowd_costs_active: bool = False
        self._sound_costs_active: bool = False
        self._player_costs_active: bool = False
        self._face_pending_routes: set = set()
        self._mode_cache = None
        self._shortcuts_active: bool = False
        self._prefer_shortcuts: bool = False
        self._player_osm_bridge_policy: Optional[Callable[[], bool]] = None

    def set_player_osm_bridge_policy(
        self, policy: Optional[Callable[[], bool]],
    ) -> None:
        """Register whether FP point-and-click may compose OSM bridges.

        When ``policy()`` is False, :meth:`RouteComposer.compose` is
        called with ``allow_osm_bridge=False`` for the threaded player
        compute — off-NavMesh clicks fail without loading the city graph.
        """
        self._player_osm_bridge_policy = policy

    def _eval_player_osm_bridge_allowed(self) -> bool:
        if self._player_osm_bridge_policy is None:
            return False
        try:
            return bool(self._player_osm_bridge_policy())
        except Exception:
            return False

    def set_mode_cache(self, mode_cache) -> None:
        """Attach the dual-mode NavMesh cache so all routes query the active mode's mesh."""
        self._mode_cache = mode_cache

    def _navmesh_override_for_route(self, route_id: str) -> Optional[object]:
        """Return the cached INavMesh handle the given route should query.

        All routes — including player point-and-click — respect the active
        mode so a wheelchair user's path-and-click also uses the wheelchair
        mesh (unreachable stairs etc.).
        """
        if self._mode_cache is None:
            return None
        return self._mode_cache.get_active_navmesh()

    def _navmesh_mode_name(self) -> Optional[str]:
        """Return the currently-active mode name ('walking'/'wheelchair') for logging."""
        if self._mode_cache is None:
            return None
        try:
            return self._mode_cache.get_active_mode()
        except Exception:
            return None

    def set_route_measure_enabled(self, enabled: bool) -> None:
        """Toggle route measure calculation (for 'move to x' only; point-and-click never measured)."""
        self._route_measure_enabled = bool(enabled)

    def get_route_measure_enabled(self) -> bool:
        return self._route_measure_enabled

    def set_shortcuts_active(self, active: bool) -> None:
        """Toggle shortcut routing for guided routes and recalc them."""
        if self._shortcuts_active == bool(active):
            return
        self._shortcuts_active = bool(active)
        print(f"[NAVMESH_ROUTE] Shortcuts active: {self._shortcuts_active}")
        for r in list(self._routes.values()):
            try:
                rid = str(r._cfg.route_id)
                want = self._shortcuts_active and rid in SHORTCUT_ROUTE_IDS
                if r._cfg.use_shortcuts != want:
                    r._cfg.use_shortcuts = want
                    r.recalc_now()
            except Exception:
                pass

    def get_shortcuts_active(self) -> bool:
        return self._shortcuts_active

    def set_prefer_shortcuts(self, active: bool) -> None:
        """Toggle "Prefer elevators" mode for guided routes and recalc them.

        Has no observable effect when ``self._shortcuts_active`` is
        False — the shortcut pre-pass never runs in that case so there
        is nothing to prefer. We still store and forward the flag so
        flipping the dev shortcuts toggle ON afterwards immediately
        applies the user's preference.
        """
        if self._prefer_shortcuts == bool(active):
            return
        self._prefer_shortcuts = bool(active)
        print(f"[NAVMESH_ROUTE] Prefer shortcuts: {self._prefer_shortcuts}")
        for r in list(self._routes.values()):
            try:
                rid = str(r._cfg.route_id)
                if rid not in SHORTCUT_ROUTE_IDS:
                    continue
                want = bool(self._prefer_shortcuts)
                if r._cfg.prefer_shortcuts != want:
                    r._cfg.prefer_shortcuts = want
                    if r._cfg.use_shortcuts:
                        r.recalc_now()
            except Exception:
                pass

    def get_prefer_shortcuts(self) -> bool:
        return self._prefer_shortcuts

    def set_cost_category_active(self, category: str, active: bool) -> None:
        """Toggle whether a cost category (crowd/sound) is included in pathfinding."""
        changed = False
        if category == "crowd":
            changed = self._crowd_costs_active != active
            self._crowd_costs_active = active
        elif category == "sound":
            changed = self._sound_costs_active != active
            self._sound_costs_active = active
        elif category == "player":
            changed = self._player_costs_active != active
            self._player_costs_active = active
        else:
            print(f"[NAVMESH_ROUTE] Unknown cost category: {category}")
            return
        if changed:
            print(f"[NAVMESH_ROUTE] Cost category '{category}' active: {active}")
            for r in list(self._routes.values()):
                try:
                    r.recalc_now()
                except Exception:
                    pass

    def update_camera_area_costs(self, area_name: str, cost: float) -> None:
        """Update the cost for a camera area. Higher cost = avoid area."""
        self._camera_area_costs[area_name] = float(cost)
        for r in list(self._routes.values()):
            try:
                r.recalc_now()
            except Exception:
                pass

    def update_camera_area_costs_batch(self, costs: Dict[str, float]) -> None:
        """Update multiple camera area costs at once."""
        self._camera_area_costs.update({k: float(v) for k, v in costs.items()})
        for r in list(self._routes.values()):
            try:
                r.recalc_now()
            except Exception:
                pass

    def update_sound_area_costs(self, area_name: str, cost: float) -> None:
        """Update the cost for a sound area. Higher cost = avoid area."""
        self._sound_area_costs[area_name] = float(cost)
        for r in list(self._routes.values()):
            try:
                r.recalc_now()
            except Exception:
                pass

    def update_sound_area_costs_batch(self, costs: Dict[str, float]) -> None:
        """Update multiple sound area costs at once."""
        self._sound_area_costs.update({k: float(v) for k, v in costs.items()})
        for r in list(self._routes.values()):
            try:
                r.recalc_now()
            except Exception:
                pass

    async def ensure_navmesh_ready(self) -> bool:
        return await wait_for_navmesh_ready(log_prefix="NAVMESH_ROUTE")

    async def change_agent_settings_and_rebake(self, agent_settings: dict) -> bool:
        return await _change_agent_settings_and_rebake(agent_settings)

    async def rebake_navmesh(self) -> bool:
        return await _rebake_navmesh()

    def recalc_all_routes(self) -> None:
        """Recalculate all active routes (called by the orchestrator after a bake)."""
        for r in list(self._routes.values()):
            try:
                r.recalc_now()
            except Exception:
                pass

    def start_route_calculation(self, startpoint_path: str, endpoint_path: str,
                               path_prim: Optional[str] = None,
                               curve_width: Optional[float] = None,
                               enable_periodic_recalc: bool = True) -> bool:
        return self.set_route_for_id(
            "default",
            startpoint_path,
            endpoint_path,
            path_prim=path_prim,
            curve_width=curve_width,
            enable_periodic_recalc=enable_periodic_recalc,
            start_use_ground=True,
            draw_path=False,
            recalc_now_if_active=True,
        )

    def set_route(
        self,
        start_ref: Any,
        end_ref: Any,
        *,
        path_prim: Optional[str] = None,
        curve_width: Optional[float] = None,
        enable_periodic_recalc: bool = True,
        start_use_ground: Optional[bool] = None,
        draw_path: Optional[bool] = None,
        recalc_now_if_active: bool = True,
    ) -> bool:
        """Backward compatible: set default route."""
        return self.set_route_for_id(
            "default",
            start_ref,
            end_ref,
            path_prim=path_prim,
            curve_width=curve_width,
            enable_periodic_recalc=enable_periodic_recalc,
            start_use_ground=start_use_ground,
            draw_path=draw_path,
            recalc_now_if_active=recalc_now_if_active,
        )

    def set_auto_move(self, route_id: str, active: bool) -> None:
        """Toggle the auto-move flag on a route instance."""
        route = self._routes.get(route_id)
        if route is not None:
            route._auto_move_active = active

    def redispatch_cached_waypoints(self, route_id: str) -> bool:
        """Re-publish the live polyline without recomposing (play / resume)."""
        route = self._routes.get(str(route_id or ""))
        if route is None:
            return False
        pts = route.get_last_path_points()
        if len(pts) < 2:
            return False
        self._dispatch_waypoints(str(route_id), True, list(pts), None, None)
        return True

    def set_route_for_id(
        self,
        route_id: str,
        start_ref: Any,
        end_ref: Any,
        *,
        path_prim: Optional[str] = None,
        curve_width: Optional[float] = None,
        enable_periodic_recalc: bool = True,
        start_use_ground: Optional[bool] = None,
        draw_path: Optional[bool] = None,
        recalc_now_if_active: bool = True,
        recalc_interval: Optional[float] = None,
        position_recalc_threshold: Optional[float] = None,
        face_direction: bool = False,
        via_points: Optional[List[Tuple[float, float, float]]] = None,
        auto_move: bool = False,
        use_composer: bool = False,
        corridor_section: Optional[str] = None,
        shortcut_eval_always: bool = False,
    ) -> bool:
        """Create/update a route identified by route_id.

        start_ref/end_ref can be USD prim paths (str) or world positions (x,y,z).

        ``use_composer=True`` switches the engine onto the
        ``RouteComposer`` path (handles NavMesh ↔ OSM bridging). Used
        by the bird-eye directions panel (``poi_nav``) so the same
        route_id can span the city graph and still go through the
        same pause / play / recalc / auto-move pipeline as seat_nav.
        """
        try:
            rid = str(route_id or "default")
            new_start = normalize_vec3_ref(start_ref)
            new_end = normalize_vec3_ref(end_ref)

            if face_direction:
                self._face_pending_routes.add(rid)

            if not path_prim:
                if rid == "default":
                    path_prim = "/World/ShortestPathCurve"
                else:
                    path_prim = f"/World/NavmeshRoutes/{_safe_prim_name(rid)}"

            existing_route = self._routes.get(rid)
            if via_points is not None:
                resolved_via = list(via_points)
            elif existing_route is not None:
                resolved_via = list(existing_route._cfg.via_points)
            else:
                resolved_via = []

            if corridor_section is not None:
                resolved_section = str(corridor_section).strip() or None
            elif existing_route is not None:
                resolved_section = getattr(
                    existing_route._cfg, "corridor_section", None,
                )
            else:
                resolved_section = None

            resolved_shortcut_eval = bool(
                shortcut_eval_always
                and self._shortcuts_active
                and rid in SHORTCUT_ROUTE_IDS
            )
            if existing_route is not None:
                resolved_shortcut_eval = resolved_shortcut_eval or bool(
                    getattr(existing_route._cfg, "shortcut_eval_always", False)
                )

            cfg = RouteConfig(
                route_id=rid,
                start_ref=new_start,
                end_ref=new_end,
                start_use_ground=bool(start_use_ground) if start_use_ground is not None else True,
                draw_path=bool(draw_path) if draw_path is not None else True,
                path_prim=str(path_prim),
                curve_width=float(curve_width) if curve_width is not None else 10.0,
                enable_periodic_recalc=bool(enable_periodic_recalc),
                recalc_interval=float(recalc_interval) if recalc_interval is not None else 5.0,
                position_recalc_threshold=float(position_recalc_threshold) if position_recalc_threshold is not None else 10.0,
                via_points=resolved_via,
                get_navmesh_override=lambda _rid=rid: self._navmesh_override_for_route(_rid),
                get_navmesh_mode=lambda: self._navmesh_mode_name(),
                use_composer=bool(use_composer),
                use_shortcuts=bool(self._shortcuts_active and rid in SHORTCUT_ROUTE_IDS),
                prefer_shortcuts=bool(self._prefer_shortcuts and rid in SHORTCUT_ROUTE_IDS),
                corridor_section=resolved_section,
                shortcut_eval_always=resolved_shortcut_eval,
            )

            route = existing_route
            is_player_route = rid in ("player", "default")
            if route is None:
                route = RouteInstance(
                    config=cfg,
                    get_camera_area_costs=lambda _p=is_player_route: dict(self._camera_area_costs) if (self._player_costs_active if _p else self._crowd_costs_active) else {},
                    get_sound_area_costs=lambda _p=is_player_route: dict(self._sound_area_costs) if (self._player_costs_active if _p else self._sound_costs_active) else {},
                    get_route_measure_enabled=lambda: self._route_measure_enabled,
                    dispatch_waypoints=self._dispatch_waypoints,
                    get_allow_player_osm_bridge=(
                        (lambda: self._eval_player_osm_bridge_allowed())
                        if rid == "player"
                        else None
                    ),
                )
                route._auto_move_active = auto_move
                self._routes[rid] = route
                route.start()
                dispatch_to_events2("navmeshRouteStatus", {"routeId": rid, "active": True})
                return True

            route._auto_move_active = auto_move
            if len(route.get_last_path_points()) >= 2:
                route._sync_arrival_aabb_from_path()
            route.update_config(cfg=cfg)
            if recalc_now_if_active:
                route.recalc_now()
            dispatch_to_events2("navmeshRouteStatus", {"routeId": rid, "active": True})
            return True
        except Exception as e:
            print(f"[NAVMESH_ROUTE] set_route_for_id error: {e}")
            return False

    def _dispatch_waypoints(
        self,
        route_id: str,
        success: bool,
        points: List[Tuple[float, float, float]],
        error: Optional[str],
        measure: Optional[RouteMeasure] = None,
    ) -> None:
        dispatch_navmesh_route_waypoints(
            routes=self._routes,
            face_pending_routes=self._face_pending_routes,
            route_id=route_id,
            success=success,
            points=points,
            error=error,
            measure=measure,
        )

    def stop_route_calculation(self) -> None:
        """Backward compatible: stop default route."""
        self.stop_route("default")

    def stop_route(self, route_id: str) -> None:
        rid = str(route_id or "default")
        route = self._routes.pop(rid, None)
        if not route:
            return
        try:
            route.stop()
        finally:
            dispatch_to_events2("navmeshRouteStatus", {"routeId": rid, "active": False})

    def stop_all_routes(self) -> None:
        for rid in list(self._routes.keys()):
            try:
                self.stop_route(rid)
            except Exception:
                pass

    def get_last_path_points(self, route_id: str = "default") -> List[Tuple[float, float, float]]:
        """Return last computed path points for a routeId."""
        route = self._routes.get(str(route_id or "default"))
        if not route:
            return []
        return route.get_last_path_points()

    def compute_routes_to_exits(
        self,
        exit_refs: List[Union[str, Tuple[float, float, float]]],
        player_ref: Any = "/World/PlayerCharacter",
        use_waypoints: bool = False,
        poi_list_cache_type: Optional[str] = None,
        on_progress: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to route measure service; one-shot player->exits for exit widget.

        When the dev "Use shortcuts" toggle is on
        (``self._shortcuts_active``) the underlying measure pre-pass
        also retries failed direct measures via
        ``RouteComposer.compose(enable_shortcuts=True)``, so
        destinations behind stairs (e.g. the lower-restaurant quiet
        zone in wheelchair mode) become visible in the POI / quiet-zone
        panels via an elevator hop. CU users are unaffected because the
        toggle stays off in production.
        """
        override = self._navmesh_override_for_route("exit_nav")
        return compute_routes_to_exits_impl(
            player_ref,
            exit_refs,
            camera_area_costs=dict(self._camera_area_costs) if self._crowd_costs_active else {},
            sound_area_costs=dict(self._sound_area_costs) if self._sound_costs_active else {},
            speed_m_per_s=DEFAULT_WALK_SPEED_M_PER_S,
            use_waypoints=use_waypoints,
            navmesh_override=override,
            enable_shortcuts=bool(self._shortcuts_active),
            prefer_shortcuts=bool(self._prefer_shortcuts),
            poi_list_cache_type=poi_list_cache_type,
            on_progress=on_progress,
        )

    def try_activate_from_poi_list_cache(
        self,
        route_id: str,
        start_ref: Any,
        end_ref: Any,
        *,
        poi_type: str,
        path_prim: Optional[str] = None,
        curve_width: Optional[float] = None,
        draw_path: bool = True,
        enable_periodic_recalc: bool = True,
        start_use_ground: bool = True,
        face_direction: bool = True,
        auto_move: bool = False,
    ) -> bool:
        """Draw a guided route from the bulk POI-list cache (no pathfinding re-query)."""
        from ..route_measure import poi_list_route_cache

        cached = poi_list_route_cache.get(poi_type, start_ref, end_ref)
        if not cached:
            return False
        points = cached.get("points")
        if not isinstance(points, list) or len(points) < 2:
            return False
        measure = cached.get("measure")
        cached_via = cached.get("via_points")
        via_points = list(cached_via) if isinstance(cached_via, list) else None
        cached_speeds = cached.get("segment_speeds")
        cached_classes = cached.get("segment_classes")
        segment_speeds = (
            list(cached_speeds)
            if isinstance(cached_speeds, list)
            else None
        )
        segment_classes = (
            list(cached_classes)
            if isinstance(cached_classes, list)
            else None
        )

        rid = str(route_id or "default")
        if face_direction:
            self._face_pending_routes.add(rid)

        if not path_prim:
            path_prim = (
                "/World/ShortestPathCurve"
                if rid == "default"
                else f"/World/NavmeshRoutes/{_safe_prim_name(rid)}"
            )

        existing = self._routes.get(rid)
        if existing is not None:
            try:
                existing.stop()
            except Exception:
                pass
            self._routes.pop(rid, None)

        ok = self.set_route_for_id(
            rid,
            start_ref,
            end_ref,
            path_prim=str(path_prim),
            curve_width=float(curve_width) if curve_width is not None else None,
            enable_periodic_recalc=bool(enable_periodic_recalc),
            start_use_ground=bool(start_use_ground),
            draw_path=bool(draw_path),
            recalc_now_if_active=False,
            face_direction=face_direction,
            auto_move=auto_move,
            via_points=via_points,
            shortcut_eval_always=bool(
                self._shortcuts_active and rid in SHORTCUT_ROUTE_IDS
            ),
        )
        route = self._routes.get(rid)
        if not route:
            return False

        try:
            if route._initial_task and not route._initial_task.done():
                route._initial_task.cancel()
        except Exception:
            pass
        route._initial_task = None

        apply_ok, out_pts, err, out_measure = route.apply_precomputed_path(
            points,
            measure if isinstance(measure, RouteMeasure) else None,
            segment_speeds=segment_speeds,
            segment_classes=segment_classes,
        )
        self._dispatch_waypoints(rid, apply_ok, out_pts, err, out_measure)
        if apply_ok:
            shortcut_tag = " shortcut" if cached.get("has_shortcut") else ""
            print(
                f"[NAVMESH_ROUTE] {rid} activated from POI-list cache "
                f"({len(out_pts)} waypoints, poiType={poi_type}{shortcut_tag})"
            )
        return apply_ok
