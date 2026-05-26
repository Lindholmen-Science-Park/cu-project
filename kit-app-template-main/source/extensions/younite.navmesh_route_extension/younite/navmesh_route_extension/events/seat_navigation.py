"""Seat navigation, teleport, layout switching, route-ready relay."""

from __future__ import annotations

import asyncio

from .wiring import NavmeshWireContext


def register(ctx: NavmeshWireContext, dispatch_view_transition_ready, dispatch_view_transition_ready_after_settle) -> None:
    ext = ctx.ext
    observe = ctx.observe
    normalize_event_payload = ctx.normalize_event_payload

    def _resolve_seat_number(payload):
        """Build seat ID from structured {section, row, seat} or legacy seatNumber string."""
        section = str(payload.get("section") or "").strip().upper()
        row = str(payload.get("row") or "").strip().upper()
        seat = str(payload.get("seat") or "").strip()
        if section and row and seat:
            return f"{section}-{row}-{seat}"
        return str(payload.get("seatNumber") or payload.get("seat_number") or "").strip()

    def _on_seat_navigate(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        seat_number = _resolve_seat_number(payload)
        if not seat_number:
            return

        action = str(payload.get("action", "navigate")).lower()
        route_id = "seat_nav"

        if action == "stop":
            from ..seat_nav_target_bridge import set_seat_nav_target_seat_id

            set_seat_nav_target_seat_id(None)
            ext._svc.stop_route(route_id)
            ext._svc.stop_route("player")
            try:
                from ..services.kit_services import seat_highlight

                seat_highlight.unhighlight_seat()
            except Exception:
                pass
            dispatch_to_events2 = None
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2
            except Exception:
                pass
            if dispatch_to_events2:
                dispatch_to_events2("seatNavigateResult", {"seatNumber": seat_number, "success": True, "action": "stop"})
            return

        from ..services.kit_services.seat_lookup import get_seat_position, is_seat_available

        pos = get_seat_position(seat_number)
        if not pos:
            print(f"[navmesh_route] Seat '{seat_number}' not found in lookup")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("seatNavigateResult", {"seatNumber": seat_number, "success": False, "error": "not_found"})
            except Exception:
                pass
            return

        if is_seat_available(seat_number) is False:
            print(f"[navmesh_route] Seat '{seat_number}' exists but is not available for this event")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("seatNavigateResult", {"seatNumber": seat_number, "success": False, "error": "not_available"})
                print(f"[navmesh_route] Dispatched not_available result for seat '{seat_number}'")
            except Exception as e:
                print(f"[navmesh_route] Failed to dispatch not_available: {e}")
            return

        try:
            from ..services.kit_services import seat_highlight

            seat_highlight.highlight_seat(seat_number)
        except Exception as e:
            print(f"[navmesh_route] Seat highlight failed: {e}")

        use_waypoints = payload.get("useWaypoints", True)
        if isinstance(use_waypoints, str):
            use_waypoints = use_waypoints.lower() not in ("false", "0", "no")
        section = str(payload.get("section") or "").strip()

        via_points = []
        if use_waypoints and section:
            try:
                import omni.usd

                from ..services.kit_services import waypoint_router
                from ..scripts.navmesh_shortest_path import resolve_position

                ctx_usd = omni.usd.get_context()
                stage = ctx_usd.get_stage() if ctx_usd else None
                if stage:
                    player_pos_gf = resolve_position(stage, "/World/PlayerCharacter", use_ground=True)
                    player_pos_t = (float(player_pos_gf[0]), float(player_pos_gf[1]), float(player_pos_gf[2]))
                    via_points = waypoint_router.plan_route(player_pos_t, pos, section)
            except Exception as e:
                print(f"[navmesh_route] Waypoint routing failed, using direct path: {e}")
                via_points = []

        print(
            f"[navmesh_route] Navigating to seat {seat_number} at ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}), "
            f"via {len(via_points)} waypoints (useWaypoints={use_waypoints})"
        )
        from ..seat_nav_target_bridge import set_seat_nav_target_seat_id

        set_seat_nav_target_seat_id(seat_number, pos)
        corridor_sec = (
            section.strip() or None
            if (use_waypoints and section)
            else None
        )
        ext._svc.set_route_for_id(
            route_id,
            "/World/PlayerCharacter",
            pos,
            draw_path=True,
            enable_periodic_recalc=True,
            start_use_ground=True,
            recalc_now_if_active=True,
            face_direction=True,
            via_points=via_points if via_points else None,
            corridor_section=corridor_sec,
        )
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2("seatNavigateResult", {"seatNumber": seat_number, "success": True, "position": list(pos)})
        except Exception:
            pass

    observe("seatNavigate", _on_seat_navigate)

    # ── Relay seat/exit/restroom route failures to the web UI ──

    def _on_route_waypoints(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        route_id = str(payload.get("routeId") or payload.get("route_id") or "")
        success = payload.get("success", True)
        pts = payload.get("points")
        pt_count = len(pts) if isinstance(pts, list) else 0
        print(
            f"[ready_dbg] navmeshRouteWaypoints observed: "
            f"routeId={route_id!r} success={success} pts={pt_count}"
        )
        if success:
            if route_id in ("seat_nav", "poi_nav", "quiet_zone_nav", "exit_nav"):
                try:
                    from younite.messaging_core_extension.message_utils import dispatch_to_events2

                    print(f"[ready_dbg] dispatching navmeshRouteReady routeId={route_id!r}")
                    dispatch_to_events2("navmeshRouteReady", {"routeId": route_id})
                except Exception as exc:
                    print(f"[ready_dbg] navmeshRouteReady dispatch failed: {exc}")
            return
        error_msg = str(payload.get("error") or "Route calculation failed")
        if error_msg in ("stopped", "recalculating"):
            return
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2("navmeshRouteError", {"routeId": route_id, "error": error_msg})
        except Exception:
            pass

    observe("navmeshRouteWaypoints", _on_route_waypoints)

    # ── Seat teleport (instant jump) ──

    def _on_seat_teleport(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        seat_number = _resolve_seat_number(payload)
        if not seat_number:
            return

        from ..seat_nav_target_bridge import set_seat_nav_target_seat_id

        set_seat_nav_target_seat_id(None)

        from ..services.kit_services.seat_lookup import (
            get_seat_position,
            is_seat_available,
            get_seat_positions_bbox_center_xz,
            camera_local_yaw_to_face_world_xz,
        )

        pos = get_seat_position(seat_number)
        if not pos:
            print(f"[navmesh_route] Seat teleport: '{seat_number}' not found")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("seatTeleportResult", {"seatNumber": seat_number, "success": False, "error": "not_found"})
            except Exception:
                pass
            dispatch_view_transition_ready(False)
            return

        if is_seat_available(seat_number) is False:
            print(f"[navmesh_route] Seat teleport: '{seat_number}' not available")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("seatTeleportResult", {"seatNumber": seat_number, "success": False, "error": "not_available"})
            except Exception:
                pass
            dispatch_view_transition_ready(False)
            return

        teleported = False
        camera_yaw = None
        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if stage:
                player_prim = stage.GetPrimAtPath("/World/PlayerCharacter")
                if player_prim and player_prim.IsValid():
                    ctr = get_seat_positions_bbox_center_xz()
                    if ctr:
                        y_calc = camera_local_yaw_to_face_world_xz(
                            player_prim,
                            float(pos[0]),
                            float(pos[2]),
                            float(ctr[0]),
                            float(ctr[1]),
                        )
                        if y_calc is not None:
                            camera_yaw = y_calc
        except Exception:
            camera_yaw = None

        try:
            from younite.usd_viewer_stage_core_extension.teleport_registry import get_teleport_service

            tp = get_teleport_service()
            if tp:
                if camera_yaw is not None:
                    teleported = tp.teleport_to_coordinates(
                        float(pos[0]),
                        float(pos[1]),
                        float(pos[2]),
                        camera_local_yaw_deg=camera_yaw,
                    )
                else:
                    teleported = tp.teleport_to_coordinates(float(pos[0]), float(pos[1]), float(pos[2]))
            else:
                print("[navmesh_route] Seat teleport: TeleportService not available")
        except Exception as e:
            print(f"[navmesh_route] Seat teleport failed: {e}")

        if teleported:
            ext._svc.stop_route("seat_nav")
            ext._svc.stop_route("player")
            try:
                from ..services.kit_services import seat_highlight

                seat_highlight.unhighlight_seat()
            except Exception:
                pass
            y_note = f", yaw={camera_yaw:.1f}" if camera_yaw is not None else ""
            print(
                f"[navmesh_route] Teleported to seat {seat_number} at "
                f"({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}){y_note}"
            )

        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2("seatTeleportResult", {"seatNumber": seat_number, "success": teleported, "position": list(pos)})
        except Exception:
            pass
        if teleported:
            asyncio.ensure_future(dispatch_view_transition_ready_after_settle(True))
        else:
            dispatch_view_transition_ready(False)

    observe("seatTeleport", _on_seat_teleport)

    def _on_player_face_stadium_center(_evt):
        """Seat-arrival UI asks Kit to yaw toward seating bbox center (XZ)."""
        try:
            from ..services.kit_services import seat_lookup
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            c = seat_lookup.get_seat_positions_bbox_center_xz()
            if c is None:
                return
            dispatch_to_events2("playerFaceWorldXZ", {"x": float(c[0]), "z": float(c[1])})
        except Exception:
            pass

    observe("playerFaceStadiumCenter", _on_player_face_stadium_center)

    # ── Seat layout variant switching ──

    def _on_seat_layout_change(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        variant_name = str(payload.get("variant") or payload.get("layout") or "").strip()

        try:
            from ..services.kit_services import seat_lookup

            available_variants = seat_lookup.get_available_variants()

            if not variant_name:
                current = seat_lookup.get_active_variant()
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("seatLayoutChanged", {
                    "variant": current or (list(available_variants.keys())[0] if available_variants else ""),
                    "success": True,
                    "variants": list(available_variants.keys()) if available_variants else [],
                })
                return

            if available_variants and variant_name not in available_variants:
                print(
                    f"[navmesh_route] Unknown seating variant '{variant_name}'. "
                    f"Available: {list(available_variants.keys())}"
                )
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("seatLayoutChanged", {
                    "variant": variant_name, "success": False, "error": "unknown_variant"
                })
                return

            import omni.usd

            ctx_usd = omni.usd.get_context()
            stage = ctx_usd.get_stage()
            if not stage:
                return

            instancer_prim = stage.GetPrimAtPath(
                "/World/Skandinavium/seats_instanced/SeatInstancer"
            )
            if not instancer_prim or not instancer_prim.IsValid():
                print("[navmesh_route] SeatInstancer prim not found for variant switch")
                return

            vsets = instancer_prim.GetVariantSets()
            if "seating" not in vsets.GetNames():
                print("[navmesh_route] No 'seating' VariantSet on SeatInstancer")
                return

            vset = vsets.GetVariantSet("seating")
            old_variant = vset.GetVariantSelection()

            try:
                from ..services.kit_services import seat_highlight

                seat_highlight.unhighlight_seat()
            except Exception:
                pass

            vset.SetVariantSelection(variant_name)
            print(f"[navmesh_route] Seating variant: '{old_variant}' -> '{variant_name}'")

            seat_lookup.set_active_variant(variant_name)

            try:
                from ..services.kit_services import seat_highlight

                seat_highlight.invalidate_cache()
            except Exception:
                pass

            try:
                from ..services.kit_services import (
                    seat_proto_override,
                    seat_fold_state,
                )

                seat_proto_override.reapply()
                seat_fold_state.refresh()
            except Exception as _e:
                print(f"[navmesh_route] Re-flush after seating variant flip failed: {_e}")

            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2("seatLayoutChanged", {
                "variant": variant_name,
                "success": True,
                "variants": list(available_variants.keys()) if available_variants else [],
            })
        except Exception as e:
            print(f"[navmesh_route] Variant switch error: {e}")

    observe("seatLayoutChange", _on_seat_layout_change)

    def _on_seated_crowd_layout_changed(evt):
        try:
            from ..services.kit_services import seated_crowd_highlight

            seated_crowd_highlight.on_variant_changed()
        except Exception as e:
            print(f"[navmesh_route] seated crowd variant reapply failed: {e}")
        try:
            from ..services.kit_services import seat_fold_state

            seat_fold_state.refresh()
        except Exception as e:
            print(f"[navmesh_route] seat fold-state refresh failed: {e}")

    observe("seatedCrowdLayoutChanged", _on_seated_crowd_layout_changed)
