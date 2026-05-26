"""Route calculation, mode switching, camera/sound/rebake area controls."""

from __future__ import annotations

import asyncio

from .helpers import compute_poi_waypoints, parse_vec3
from .wiring import NavmeshWireContext

# ``fromPoiList`` on navmeshRouteCalculate → bulk-list cache (restroom / quiet-zone).
POI_LIST_CACHE_BY_ROUTE_ID = {
    "poi_nav": "restroom",
    "quiet_zone_nav": "quiet_zone",
}


def register(ctx: NavmeshWireContext) -> None:
    ext = ctx.ext
    observe = ctx.observe
    normalize_event_payload = ctx.normalize_event_payload
    carb = ctx.carb

    # ── Player ready: pre-bake only when not in bird's-eye (navmesh unused there) ──

    def _camera_view_type_is_bird_eye() -> bool:
        try:
            s = carb.settings.get_settings()
            vt = str(s.get("/younite/camera/viewType") or "firstPerson")
            return vt == "birdEye"
        except Exception:
            return False

    def _on_player_ready(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            if not bool(payload.get("success", True)):
                return
            if _camera_view_type_is_bird_eye():
                print(
                    "[navmesh_route] Player ready -> skip navmesh pre-bake (bird's-eye); "
                    "first FP spawn will bake via stage_core"
                )
                return
            if ext._mode_cache.is_ready():
                print("[navmesh_route] Player ready -> dual-mode cache already ready, skipping")
                return
            print("[navmesh_route] Player ready -> baking dual-mode navmeshes (wheelchair + walking)...")
            if ext._initial_bake_task is None or ext._initial_bake_task.done():
                ext._initial_bake_task = asyncio.ensure_future(ext._orchestrator.request_rebake())
        except Exception as e:
            print(f"[navmesh_route] Pre-bake trigger failed: {e}")

    observe("younite.player.ready", _on_player_ready)

    # ── Route calculation ──

    def _on_calc(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        route_id = str(payload.get("routeId") or payload.get("route_id") or "default")
        start_pos = parse_vec3(payload, ["startPos", "startPosition", "startWorldPos", "startPoint"])
        end_pos = parse_vec3(payload, ["endPos", "endPosition", "endWorldPos", "endPoint", "targetPos", "targetPosition"])

        start = start_pos if start_pos is not None else str(
            payload.get("startpointPath") or payload.get("start") or "/World/PlayerCharacter"
        )
        end = end_pos if end_pos is not None else str(
            payload.get("endpointPath") or payload.get("end") or "/World/EndPoint_Cube"
        )

        path_prim = payload.get("pathPrim") or payload.get("path_prim")
        curve_width = payload.get("curveWidth") or payload.get("curve_width")
        draw_path = payload.get("drawPath")
        if draw_path is None:
            draw_path = payload.get("showPath")
        if draw_path is None:
            draw_path = False

        enable_periodic_recalc = payload.get("enablePeriodicRecalc")
        if enable_periodic_recalc is None:
            enable_periodic_recalc = True
        start_use_ground = payload.get("startUseGround")
        if start_use_ground is None:
            start_use_ground = True
        camera_area_costs = payload.get("cameraAreaCosts")
        if isinstance(camera_area_costs, dict):
            ext._svc.update_camera_area_costs_batch(camera_area_costs)
        is_user_route = route_id not in ("player", "default")
        auto_move = bool(payload.get("autoMove", False))

        use_composer = bool(payload.get("useComposer", False))
        from_poi_list = bool(
            payload.get("fromPoiList") or payload.get("from_poi_list"),
        )
        poi_type_for_cache = ""
        if from_poi_list:
            poi_type_for_cache = POI_LIST_CACHE_BY_ROUTE_ID.get(route_id, "")

        # Bulk-list cache only for the first "Get directions" draw. Pause/Play
        # must not reload the original polyline (resets progress + camera yaw).
        existing_route = (
            ext._svc._routes.get(route_id) if is_user_route else None
        )
        has_live_path = (
            existing_route is not None
            and len(existing_route.get_last_path_points()) >= 2
        )
        # Orchestrator play/pause re-dispatches navmeshRouteCalculate on every
        # navigationStateSet; only toggle auto-move on the cached polyline.
        auto_move_toggle_only = bool(
            has_live_path and not from_poi_list and is_user_route,
        )

        via_points = None
        explicit_via = payload.get("viaPoints") or payload.get("via_points")
        if isinstance(explicit_via, (list, tuple)):
            parsed_via: list[tuple[float, float, float]] = []
            for entry in explicit_via:
                if isinstance(entry, (list, tuple)) and len(entry) >= 3:
                    try:
                        parsed_via.append((float(entry[0]), float(entry[1]), float(entry[2])))
                    except Exception:
                        continue
            if parsed_via:
                via_points = parsed_via
        if (
            via_points is None
            and route_id in ctx.waypoint_route_ids
            and not auto_move_toggle_only
        ):
            via_points = compute_poi_waypoints(start, end)

        use_poi_cache = bool(poi_type_for_cache and is_user_route and not has_live_path)

        if auto_move_toggle_only:
            ext._svc.set_auto_move(route_id, auto_move)
            # Auto-mover ignores waypoints until ``routeId`` matches; Get
            # directions often dispatches before Play sets poi_nav.
            if auto_move:
                ext._svc.redispatch_cached_waypoints(route_id)
            return

        if use_poi_cache:
            if ext._svc.try_activate_from_poi_list_cache(
                route_id,
                start,
                end,
                poi_type=poi_type_for_cache,
                path_prim=str(path_prim) if path_prim else None,
                curve_width=float(curve_width) if curve_width is not None else None,
                draw_path=bool(draw_path),
                enable_periodic_recalc=bool(enable_periodic_recalc),
                start_use_ground=bool(start_use_ground),
                face_direction=is_user_route,
                auto_move=auto_move,
            ):
                return

        raw_sec = payload.get("corridorSection") or payload.get(
            "corridor_section",
        )
        corridor_section_payload = (
            str(raw_sec).strip() or None
            if isinstance(raw_sec, str)
            else None
        )

        ext._svc.set_route_for_id(
            route_id,
            start,
            end,
            path_prim=str(path_prim) if path_prim else None,
            curve_width=float(curve_width) if curve_width is not None else None,
            enable_periodic_recalc=bool(enable_periodic_recalc),
            start_use_ground=bool(start_use_ground),
            draw_path=bool(draw_path),
            recalc_now_if_active=True,
            face_direction=is_user_route and not has_live_path,
            auto_move=auto_move,
            via_points=via_points if via_points else None,
            use_composer=use_composer,
            corridor_section=corridor_section_payload,
        )

    def _on_camera_area_cost(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        area_name = payload.get("areaName") or payload.get("area_name")
        cost = payload.get("cost")
        if area_name is not None and cost is not None:
            ext._svc.update_camera_area_costs(str(area_name), float(cost))

    def _on_stop(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        if bool(payload.get("all")):
            from ..seat_nav_target_bridge import set_seat_nav_target_seat_id

            set_seat_nav_target_seat_id(None)
            ext._svc.stop_all_routes()
            return
        route_id = payload.get("routeId") or payload.get("route_id")
        if route_id:
            rid = str(route_id)
            if rid == "seat_nav":
                from ..seat_nav_target_bridge import set_seat_nav_target_seat_id

                set_seat_nav_target_seat_id(None)
            ext._svc.stop_route(rid)
        else:
            ext._svc.stop_route_calculation()

    def _on_auto_move_status(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        route_id = str(payload.get("routeId") or "")
        active = bool(payload.get("active", False))
        if route_id:
            ext._svc.set_auto_move(route_id, active)
            if not active:
                route = ext._svc._routes.get(route_id)
                if route is not None:
                    route.recalc_now()

    observe("navmeshRouteCalculate", _on_calc)
    observe("navmeshRouteStop", _on_stop)
    observe("navmeshCameraAreaCostUpdate", _on_camera_area_cost)
    observe("autoMoveStatus", _on_auto_move_status)

    # ── Walking / Wheelchair mode ──

    def _on_mode_set(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        mode = str(payload.get("mode") or "").strip().lower()
        from younite.messaging_core_extension.message_utils import dispatch_to_events2 as d2e

        if mode not in ("walking", "wheelchair"):
            print(f"[navmesh_route] Ignoring unknown mode '{mode}'")
            return

        if not ext._mode_cache.is_ready():
            print(
                f"[navmesh_route] Mode switch to '{mode}' rejected: "
                "dual-mode cache not ready (initial bake still pending or failed)"
            )
            d2e("navmeshModeStatus", {"mode": mode, "status": "error"})
            return

        ok = ext._mode_cache.set_active_mode(mode)
        if ok:
            ext._svc.recalc_all_routes()
        d2e("navmeshModeStatus", {
            "mode": mode,
            "status": "ready" if ok else "error",
        })

    observe("navmeshModeSet", _on_mode_set)

    # ── Camera data calc toggle ──

    def _on_camera_data_calc_toggle(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            active = bool(payload.get("active", False))
            ext._camera_provider.set_active(active)

            async def _do():
                from younite.messaging_core_extension.message_utils import dispatch_to_events2 as d2e
                from ..scripts.camera_navmesh_areas import get_camera_area_names

                area_names = list(get_camera_area_names().values())
                d2e("cameraDataCalcStatus", {
                    "active": active,
                    "status": "baking",
                    "areaNames": area_names,
                })

                if not active:
                    ext._camera_provider.remove_areas()

                ok = await ext._orchestrator.request_rebake()

                d2e("cameraDataCalcStatus", {
                    "active": active,
                    "status": "ready" if ok else "error",
                    "areaNames": area_names if active else [],
                })

            asyncio.ensure_future(_do())
        except Exception as e:
            print(f"[navmesh_route] cameraDataCalcToggle failed: {e}")

    def _on_show_camera_areas(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            visible = bool(payload.get("visible", True))
            ext._camera_provider.set_show_areas(visible)
            print(f"[navmesh_route] Camera area cubes visibility: {visible}")
        except Exception as e:
            print(f"[navmesh_route] showNavmeshCameraAreasRequest failed: {e}")

    observe("showNavmeshCameraAreasRequest", _on_show_camera_areas)
    observe("cameraDataCalcToggle", _on_camera_data_calc_toggle)

    # ── Sound area controls (mirrors camera pattern) ──

    def _on_show_sound_areas(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            visible = bool(payload.get("visible", True))
            ext._sound_provider.set_show_areas(visible)
            print(f"[navmesh_route] Sound area visibility: {visible}")
        except Exception as e:
            print(f"[navmesh_route] showSoundAreasRequest failed: {e}")

    def _on_sound_data_calc_toggle(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            active = bool(payload.get("active", False))
            ext._sound_provider.set_active(active)

            async def _do():
                from younite.messaging_core_extension.message_utils import dispatch_to_events2 as d2e
                from younite.sound_area_extension.scripts.sound_navmesh_areas import get_sound_location_names

                area_names = list(get_sound_location_names().values())
                d2e("soundDataCalcStatus", {
                    "active": active,
                    "status": "baking",
                    "areaNames": area_names,
                })

                if not active:
                    ext._sound_provider.remove_areas()

                ok = await ext._orchestrator.request_rebake()

                d2e("soundDataCalcStatus", {
                    "active": active,
                    "status": "ready" if ok else "error",
                    "areaNames": area_names if active else [],
                })

            asyncio.ensure_future(_do())
        except Exception as e:
            print(f"[navmesh_route] soundDataCalcToggle failed: {e}")

    def _on_sound_area_cost(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        area_name = payload.get("areaName") or payload.get("area_name")
        cost = payload.get("cost")
        if area_name is not None and cost is not None:
            ext._svc.update_sound_area_costs(str(area_name), float(cost))

    observe("showSoundAreasRequest", _on_show_sound_areas)
    observe("soundDataCalcToggle", _on_sound_data_calc_toggle)
    observe("soundAreaCostUpdate", _on_sound_area_cost)

    # ── Cost category toggle (crowd/sound inclusion in pathfinding) ──

    def _on_cost_category_toggle(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            category = str(payload.get("category", "")).lower()
            active = bool(payload.get("active", False))
            ext._svc.set_cost_category_active(category, active)
        except Exception as e:
            print(f"[navmesh_route] navmeshCostCategoryToggle failed: {e}")

    observe("navmeshCostCategoryToggle", _on_cost_category_toggle)

    # ── Camera depth obstacle area visibility ──

    def _on_show_camera_depth_areas(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            visible = bool(payload.get("visible", True))
            ext._camera_depth_provider.set_show_areas(visible)
            print(f"[navmesh_route] Camera depth areas visibility: {visible}")
        except Exception as e:
            print(f"[navmesh_route] showCameraDepthAreasRequest failed: {e}")

    observe("showCameraDepthAreasRequest", _on_show_camera_depth_areas)

    # ── Generic rebake request (from incidents, etc.) ──

    def _on_rebake_request(evt):
        asyncio.ensure_future(ext._orchestrator.request_rebake())

    observe("navmeshRebakeRequest", _on_rebake_request)
