"""Bird's-eye dashed route preview, pin-at-prim, and waypoint fallback path."""

from __future__ import annotations

from .helpers import parse_vec3
from .wiring import NavmeshWireContext


def register(ctx: NavmeshWireContext) -> None:
    ext = ctx.ext
    observe = ctx.observe
    normalize_event_payload = ctx.normalize_event_payload
    carb = ctx.carb
    subs = ext._subs
    ed = ctx.ed

    def _resolve_bird_eye_start(payload):
        """Resolve start reference from payload or stored FP position."""
        start_pos = parse_vec3(payload, ["startPos"])
        if start_pos:
            return start_pos
        start_sp = payload.get("startSpawnPoint")
        if start_sp:
            leaf = str(start_sp).strip()
            try:
                import omni.usd

                from ..scripts.navmesh_shortest_path.position_resolve import (
                    resolve_spawn_prim_path_by_leaf_name,
                )

                stage = omni.usd.get_context().get_stage()
                if stage:
                    resolved = resolve_spawn_prim_path_by_leaf_name(stage, leaf)
                    if resolved:
                        return resolved
            except Exception:
                pass
            return f"/World/{leaf}"
        try:
            s = carb.settings.get_settings()
            if s.get("/younite/player/lastFpPosValid"):
                return (
                    float(s.get("/younite/player/lastFpPosX") or 0),
                    float(s.get("/younite/player/lastFpPosY") or 0),
                    float(s.get("/younite/player/lastFpPosZ") or 0),
                )
        except Exception:
            pass
        return "/World/PlayerCharacter"

    def _resolve_bird_eye_world(ref):
        """Resolve a ref (tuple Vec3 or prim path str) to a world Vec3."""
        if isinstance(ref, tuple):
            return (float(ref[0]), float(ref[1]), float(ref[2]))
        if isinstance(ref, (list,)) and len(ref) >= 3:
            return (float(ref[0]), float(ref[1]), float(ref[2]))
        if isinstance(ref, str):
            try:
                import omni.usd

                from ..scripts.navmesh_shortest_path import resolve_position

                stage = omni.usd.get_context().get_stage()
                if stage is None:
                    return None
                gf = resolve_position(stage, ref, use_ground=False)
                return (float(gf[0]), float(gf[1]), float(gf[2]))
            except Exception as exc:
                print(f"[navmesh_route] bird_eye_route: resolve ref '{ref}' failed: {exc}")
                return None
        return None

    def _compute_bird_eye_waypoints(start_ref, end_ref, payload):
        """Compute corridor waypoints for bird's-eye route."""
        try:
            import omni.usd

            from ..services.kit_services import waypoint_router
            from ..scripts.navmesh_shortest_path import resolve_position

            ctx_usd = omni.usd.get_context()
            stage = ctx_usd.get_stage() if ctx_usd else None
            if not stage:
                return None

            if isinstance(start_ref, (tuple, list)):
                player_t = (float(start_ref[0]), float(start_ref[1]), float(start_ref[2]))
            else:
                gf = resolve_position(stage, start_ref, use_ground=True)
                player_t = (float(gf[0]), float(gf[1]), float(gf[2]))

            if isinstance(end_ref, (tuple, list)):
                target_t = (float(end_ref[0]), float(end_ref[1]), float(end_ref[2]))
            else:
                gf = resolve_position(stage, end_ref, use_ground=False)
                target_t = (float(gf[0]), float(gf[1]), float(gf[2]))

            section = str(payload.get("section") or "").strip().upper()
            if section:
                wps = waypoint_router.plan_route(player_t, target_t, section)
            else:
                wps = waypoint_router.plan_route_to_position(player_t, target_t)

            return wps if wps else None
        except Exception as e:
            print(f"[navmesh_route] bird_eye_route waypoint calc failed: {e}")
            return None

    def _on_bird_eye_route_request(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})

        try:
            ext._bird_eye_route.clear_pin_marker()
        except Exception:
            pass

        try:
            ext._svc.stop_route("bird_eye")
        except Exception:
            pass

        start_ref = _resolve_bird_eye_start(payload)
        start_world = _resolve_bird_eye_world(start_ref)

        end_pos = parse_vec3(payload, ["endPos"])
        end_sp = payload.get("endSpawnPoint")
        end_seat = payload.get("endSeatNumber")
        use_waypoints = payload.get("useWaypoints", False)

        if end_pos:
            end_ref = end_pos
        elif end_seat:
            from ..services.kit_services.seat_lookup import get_seat_position

            seat_pos = get_seat_position(str(end_seat))
            if not seat_pos:
                print(f"[navmesh_route] bird_eye_route: seat '{end_seat}' not found")
                return
            end_ref = seat_pos
        elif end_sp:
            leaf = str(end_sp).strip()
            try:
                import omni.usd

                from ..scripts.navmesh_shortest_path.position_resolve import (
                    resolve_spawn_prim_path_by_leaf_name,
                )

                stage = omni.usd.get_context().get_stage()
                if stage:
                    resolved = resolve_spawn_prim_path_by_leaf_name(stage, leaf)
                    end_ref = resolved if resolved else f"/World/{leaf}"
                else:
                    end_ref = f"/World/{leaf}"
            except Exception:
                end_ref = f"/World/{leaf}"
        elif payload.get("endpointPath"):
            end_ref = str(payload.get("endpointPath")).strip()
        else:
            end_ref = "/World/PlayerCharacter"

        end_world = _resolve_bird_eye_world(end_ref)

        print(
            f"[birdeye_dbg] request: start_ref={start_ref!r} end_ref={end_ref!r} "
            f"start_world={start_world!r} end_world={end_world!r} "
            f"useWaypoints={use_waypoints}"
        )

        if start_world is None or end_world is None:
            print("[birdeye_dbg] aborting: start_world or end_world is None")
            try:
                ext._bird_eye_route.clear_route()
                ext._bird_eye_route.clear_osm_segment()
                ext._bird_eye_route.clear_route_endpoints()
            except Exception:
                pass
            return

        if use_waypoints:
            via_points = _compute_bird_eye_waypoints(start_ref, end_ref, payload)
            try:
                ext._bird_eye_route.clear_osm_segment()
            except Exception:
                pass
            try:
                ext._bird_eye_route.set_route_endpoints(start_world, end_world)
            except Exception:
                pass
            ext._svc.set_route_for_id(
                "bird_eye",
                start_ref,
                end_ref,
                draw_path=False,
                auto_move=False,
                enable_periodic_recalc=True,
                start_use_ground=True,
                face_direction=False,
                via_points=via_points if via_points else None,
            )
            return

        composer = getattr(ext, "_route_composer", None)
        if composer is None:
            print("[navmesh_route] bird_eye_route: composer unavailable")
            try:
                ext._bird_eye_route.clear_route()
                ext._bird_eye_route.clear_osm_segment()
                ext._bird_eye_route.clear_route_endpoints()
            except Exception:
                pass
            return

        composed = composer.compose(
            start_world,
            end_world,
            enable_corridor_routing=True,
        )
        if composed is None or not composed.polyline:
            print(
                f"[birdeye_dbg] composer returned no route "
                f"(composed={composed is not None})"
            )
            try:
                ext._bird_eye_route.clear_route()
                ext._bird_eye_route.clear_osm_segment()
                ext._bird_eye_route.clear_route_endpoints()
            except Exception:
                pass
            return

        nm_pts = composed.navmesh_points
        osm_pts = composed.osm_points
        print(
            f"[birdeye_dbg] composed ok: legs={len(composed.legs)} "
            f"polyline={len(composed.polyline)} "
            f"nm_pts={len(nm_pts)} osm_pts={len(osm_pts)} "
            f"start_island={composed.start_island} end_island={composed.end_island}"
        )

        try:
            if nm_pts:
                ext._bird_eye_route.on_route_computed(nm_pts)
            else:
                ext._bird_eye_route.clear_route()
            if osm_pts:
                ext._bird_eye_route.set_osm_segment(osm_pts)
            else:
                ext._bird_eye_route.clear_osm_segment()
            poly = composed.polyline
            if poly and len(poly) >= 2:
                ext._bird_eye_route.set_route_endpoints(poly[0], poly[-1])
            else:
                ext._bird_eye_route.clear_route_endpoints()
        except Exception as exc:
            print(f"[navmesh_route] bird_eye_route: projector push failed: {exc}")

        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2 as _d2e,
            )

            _d2e("navmeshRouteMeasure", {
                "routeId": "poi_nav",
                "success": True,
                "distanceMetersBase": composed.distance_meters,
                "estimatedTimeSecondsBase": composed.estimated_time_seconds,
                "distanceMetersActual": composed.distance_meters,
                "estimatedTimeSecondsActual": composed.estimated_time_seconds,
            })
        except Exception:
            pass

    def _on_bird_eye_route_clear(evt):
        ext._svc.stop_route("bird_eye")
        ext._bird_eye_route.clear_route()
        try:
            ext._bird_eye_route.clear_pin_marker()
        except Exception:
            pass
        try:
            ext._bird_eye_route.clear_osm_segment()
        except Exception:
            pass
        try:
            ext._bird_eye_route.clear_route_endpoints()
        except Exception:
            pass

    def _on_bird_eye_waypoints(evt):
        """Internal: intercept navmeshRouteWaypoints for bird_eye routeId."""
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        rid = str(payload.get("routeId") or "")
        if rid != "bird_eye":
            return
        if not payload.get("success", False):
            ext._bird_eye_route.clear_route()
            return
        raw_pts = payload.get("points") or []
        pts_3d = [(float(p[0]), float(p[1]), float(p[2])) for p in raw_pts if len(p) >= 3]
        if pts_3d:
            ext._bird_eye_route.on_route_computed(pts_3d)

    def _on_bird_eye_pin_show_at_prim(evt):
        """Show the bird-eye flag bubble at a known POI prim's xform."""
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            prim_path = str(payload.get("primPath") or payload.get("prim_path") or "").strip()
            if not prim_path:
                return
            import omni.usd
            from pxr import UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                return
            xformable = UsdGeom.Xformable(prim)
            world_mtx = xformable.ComputeLocalToWorldTransform(0)
            pos = world_mtx.ExtractTranslation()
            ext._bird_eye_route.set_pin_marker((float(pos[0]), float(pos[1]), float(pos[2])))
        except Exception as e:
            print(f"[navmesh_route] birdEyePinShowAtPrim failed: {e}")

    observe("birdEyeRouteRequest", _on_bird_eye_route_request)
    observe("birdEyeRouteClear", _on_bird_eye_route_clear)
    observe("birdEyePinShowAtPrim", _on_bird_eye_pin_show_at_prim)

    subs.append(
        ed.observe_event(
            observer_name="younite.navmesh_route_extension/birdEyeWaypoints",
            event_name="navmeshRouteWaypoints",
            on_event=_on_bird_eye_waypoints,
            order=0,
        )
    )
