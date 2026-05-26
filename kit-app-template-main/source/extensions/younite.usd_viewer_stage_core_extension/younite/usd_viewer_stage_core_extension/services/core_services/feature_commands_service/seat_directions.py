"""
Seat directions & seat teleport flows from the bird-eye view.

The seat-navigation widget reuses the same ``MapMarkerDirectionsPanel``
UI as POI directions when triggered from bird-eye (see
``SeatNavigateWidget.handleGo``). This handler is the seat-equivalent
of ``MapMarkerDirectionsHandler``:

* not swapped (current → seat): enter FP at stored FP, route to seat pos
* swapped     (seat → current): teleport to seat,    route to stored FP

Both cases use ``poi_nav`` so the POI auto-move pill takes over once
the user is in first-person — same UX as the Foyer flow. The
resolved end position is echoed back via ``seatDirectionsResolved``
so the web side can recalculate against the correct point on play /
pause.

``_on_seat_teleport_from_bird_eye_check`` is a synchronous preflight
that validates the seat (exists / available) without changing any
state, and is awaited by the web client before the fade-to-black
view transition starts. Without it an invalid seat would leave the
user stuck on a black "Entering first person…" overlay forever.
"""
from __future__ import annotations

import asyncio


class SeatDirectionsHandler:
    """Orchestrates bird-eye seat navigation & seat teleport."""

    def __init__(self, service):
        self._svc = service

    # ------------------------------------------------------------------
    # Seat directions (routed)
    # ------------------------------------------------------------------

    def on_directions_start(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            route_id = str(payload.get("routeId") or "poi_nav").strip() or "poi_nav"
            route_key = str(payload.get("routeKey") or "").strip()
            seat = payload.get("seat") or {}
            section = str(seat.get("section") or "").strip().upper()
            row = str(seat.get("row") or "").strip().upper()
            seat_num = str(seat.get("seat") or "").strip()
            if not (section and row and seat_num):
                return
            seat_id = f"{section}-{row}-{seat_num}"
            start_is_seat = bool(payload.get("startIsSeat"))
            end_use_stored_fp = bool(payload.get("endUseStoredFp"))

            asyncio.ensure_future(
                self._run_directions(
                    route_id,
                    route_key,
                    seat_id,
                    start_is_seat,
                    end_use_stored_fp,
                )
            )
        except Exception:
            pass

    async def _run_directions(
        self,
        route_id: str,
        route_key: str,
        seat_id: str,
        start_is_seat: bool,
        end_use_stored_fp: bool,
    ) -> None:
        svc = self._svc
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )
            from younite.navmesh_route_extension.services.kit_services.seat_lookup import (
                get_seat_position,
            )

            seat_pos = get_seat_position(seat_id)
            if not seat_pos:
                print(
                    f"[feature_commands] seat directions: seat '{seat_id}' not found"
                )
                return

            if svc.world_state:
                try:
                    svc.world_state.set("cameraViewType", "firstPerson")
                except Exception:
                    pass

            # Capture stored FP BEFORE _async_first_person_enter wipes it —
            # we need it both as the route destination in the swap case AND
            # as the "player start" reference for waypoint-router (both
            # branches). Without this the player ends up at the stored FP
            # but the waypoint call below runs with no reference and falls
            # back to a shortcut route that cuts through walls.
            stored_fp_pos = None
            stored = svc.fp_state.read()
            if stored:
                pos = stored.get("pos") or (0.0, 0.0, 0.0)
                stored_fp_pos = [float(pos[0]), float(pos[1]), float(pos[2])]
            end_pos = (
                list(stored_fp_pos)
                if (end_use_stored_fp and stored_fp_pos)
                else None
            )

            # Both branches first enter first-person at the player's
            # stored FP location (handles view + LOD + navmesh prep).
            # The `viewTransitionReady` dispatch is deferred until AFTER
            # the route is calculated below — the black overlay must
            # stay up until waypoints exist, otherwise the user fades
            # into the scene before the route spheres are drawn and
            # sees an empty FAB / no-op play button while Kit is still
            # pathfinding.
            #
            # For the swap case we then immediately delegate to the
            # existing `seatTeleport` handler, which moves the player
            # to the seat with the proper face-arena yaw — same path
            # the seat widget uses in first-person, so behaviour
            # matches exactly.
            fp_ok = await svc.async_first_person_enter("", dispatch_ready=False)
            if not fp_ok:
                return

            if start_is_seat:
                # Swap case: teleport to the seat first, then re-highlight.
                # The `seatTeleport` handler in
                # `younite.navmesh_route_extension` unhighlights the
                # seat after a teleport (correct for the "I arrived at
                # my seat" UX), but for swap directions the seat is
                # the *origin* of the route — the player walks AWAY
                # from it — so it must stay green throughout the
                # seat_nav route. Awaiting a couple of frames lets the
                # async seatTeleport handler complete its unhighlight
                # call before we re-apply ours.
                self._dispatch_seat_teleport(seat_id)
                try:
                    import omni.kit.app as kit_app

                    for _ in range(3):
                        await kit_app.get_app().next_update_async()
                except Exception:
                    pass

            # Highlight the destination (or origin, in swap mode) seat
            # for the duration of the seat_nav route. Mirrors the
            # first-person seat navigation flow (`_on_seat_navigate`
            # highlights on the incoming request). Must run AFTER
            # `_async_first_person_enter` because the bird-eye LOD
            # deactivates `/World/Skandinavium/seats_instanced/SeatInstancer`
            # — writing protoIndices on an inactive prim wouldn't take.
            # The matching `seatNavigate { action: 'stop' }` (sent on
            # arrival / dismiss in navigationHandlers.ts) clears the
            # highlight later.
            try:
                from younite.navmesh_route_extension.services.kit_services import (
                    seat_highlight,
                )

                seat_highlight.highlight_seat(seat_id)
            except Exception as e:
                print(f"[feature_commands] seat directions seat highlight failed: {e}")

            target_pos = (
                end_pos
                if start_is_seat
                else [float(seat_pos[0]), float(seat_pos[1]), float(seat_pos[2])]
            )
            if not target_pos:
                return

            via_points_payload = self._plan_corridor_waypoints(
                seat_id=seat_id,
                seat_pos=seat_pos,
                stored_fp_pos=stored_fp_pos,
                start_is_seat=start_is_seat,
            )

            route_payload = {
                "routeId": route_id,
                "startpointPath": "/World/PlayerCharacter",
                "endPos": target_pos,
                "drawPath": True,
                "enablePeriodicRecalc": True,
                "startUseGround": True,
            }
            if via_points_payload:
                route_payload["viaPoints"] = via_points_payload
                sec_letter = (
                    seat_id.split("-", 1)[0].strip().upper() if seat_id else ""
                )
                if sec_letter:
                    route_payload["corridorSection"] = sec_letter
            dispatch_to_events2("navmeshRouteCalculate", route_payload)

            # Echo resolved destination so the web can wire up the seat
            # overlay — `kind='seat'` + `seatKey` lets the listener
            # route the response into seat state (`activeSeatRouteId` +
            # `lastSeatPositionRef`) instead of POI state, which would
            # otherwise label the overlay as "Find toilets" by default.
            try:
                dispatch_to_events2(
                    "seatDirectionsResolved",
                    {
                        "kind": "seat",
                        "routeKey": route_key,
                        "seatKey": seat_id,
                        "endPos": target_pos,
                    },
                )
            except Exception:
                pass

            # Hold the black view-transition overlay until waypoints
            # have been generated (or the route has failed). This
            # guarantees the user fades into a scene that already has
            # the route spheres drawn — no flicker of an empty FAB /
            # no-op play button.
            await svc.await_navmesh_route_settled(route_id)
            svc.dispatch_view_transition_ready(
                "firstPerson", True, "", spawn_point=""
            )
        except Exception as exc:
            print(f"[feature_commands] seat directions start failed: {exc}")
            svc.dispatch_view_transition_ready(
                "firstPerson", False, str(exc), spawn_point=""
            )

    def _plan_corridor_waypoints(
        self,
        *,
        seat_id: str,
        seat_pos,
        stored_fp_pos: "list[float] | None",
        start_is_seat: bool,
    ) -> "list[list[float]] | None":
        """Compute section-aware corridor waypoints for the seat route.

        Without this the engine picks the shortest straight-line
        NavMesh path, which for upper-section seats cuts through walls
        and stadium geometry. ``plan_route`` is directional
        (outside-approacher → seat). For the swap case the player is
        at the seat, so we reverse the list to get: seat → section
        branch → staircase → ring → entrance → FP. Either way the FP
        position is the "outside" anchor — ``plan_route`` uses it only
        to pick the nearest entrance/ring waypoint, which is identical
        in either direction.
        """
        try:
            section_letter = (
                seat_id.split("-", 1)[0].strip().upper() if seat_id else ""
            )
            if not (section_letter and stored_fp_pos):
                print(
                    f"[feature_commands] seat directions: skipping waypoints "
                    f"(section='{section_letter}', stored_fp={bool(stored_fp_pos)})"
                )
                return None

            from younite.navmesh_route_extension.services.kit_services import (
                waypoint_router,
            )

            fp_ref = (
                float(stored_fp_pos[0]),
                float(stored_fp_pos[1]),
                float(stored_fp_pos[2]),
            )
            seat_ref = (
                float(seat_pos[0]),
                float(seat_pos[1]),
                float(seat_pos[2]),
            )
            forward = waypoint_router.plan_route(fp_ref, seat_ref, section_letter) or []
            if not forward:
                print(
                    f"[feature_commands] seat directions: plan_route returned no "
                    f"waypoints (section={section_letter})"
                )
                return None
            via_list = list(reversed(forward)) if start_is_seat else list(forward)
            print(
                f"[feature_commands] seat directions waypoints: "
                f"{len(via_list)} via-points "
                f"(section={section_letter}, swap={start_is_seat})"
            )
            return [list(v) for v in via_list]
        except Exception as exc:
            print(f"[feature_commands] seat directions waypoint plan failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Seat teleport (from bird-eye)
    # ------------------------------------------------------------------
    #
    # The plain `seatTeleport` event (handled in
    # `younite.navmesh_route_extension`) only moves the player — calling
    # it from bird-eye leaves the camera in the overhead view with the
    # light-LOD stadium. This handler first switches to first-person
    # (view + LOD + navmesh prep) and then dispatches the regular
    # `seatTeleport` so the proven face-arena yaw + seat-highlight
    # cleanup logic runs unchanged.

    def on_teleport_from_bird_eye_check(self, event) -> None:
        """Synchronous preflight: validate the seat without changing state.

        Echoes the result back via
        ``seatTeleportFromBirdEyeCheckResult``. The web client awaits
        this response before starting the fade-to-black view
        transition — otherwise an invalid seat would leave the user
        stuck on a black "Entering first person…" overlay forever.
        """
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            section = str(payload.get("section") or "").strip().upper()
            row = str(payload.get("row") or "").strip().upper()
            seat_num = str(payload.get("seat") or "").strip()
            request_id = str(payload.get("requestId") or "")
            seat_id = (
                f"{section}-{row}-{seat_num}"
                if (section and row and seat_num)
                else ""
            )

            def _respond(ok: bool, error: str = "") -> None:
                try:
                    dispatch_to_events2(
                        "seatTeleportFromBirdEyeCheckResult",
                        {
                            "requestId": request_id,
                            "ok": bool(ok),
                            "error": error,
                            "seatNumber": seat_id,
                        },
                    )
                except Exception:
                    pass

            if not seat_id:
                _respond(False, "invalid_input")
                return

            from younite.navmesh_route_extension.services.kit_services.seat_lookup import (
                get_seat_position,
                is_seat_available,
            )

            if not get_seat_position(seat_id):
                _respond(False, "not_found")
                return
            if is_seat_available(seat_id) is False:
                _respond(False, "not_available")
                return
            _respond(True)
        except Exception as exc:
            print(f"[feature_commands] seat teleport preflight failed: {exc}")

    def on_teleport_from_bird_eye(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            section = str(payload.get("section") or "").strip().upper()
            row = str(payload.get("row") or "").strip().upper()
            seat_num = str(payload.get("seat") or "").strip()
            if not (section and row and seat_num):
                return
            seat_id = f"{section}-{row}-{seat_num}"
            asyncio.ensure_future(self._run_teleport_from_bird_eye(seat_id))
        except Exception:
            pass

    async def _run_teleport_from_bird_eye(self, seat_id: str) -> None:
        svc = self._svc
        try:
            from younite.navmesh_route_extension.services.kit_services.seat_lookup import (
                get_seat_position,
            )

            # Validate up front — pointless to fade out and switch view
            # if the seat doesn't exist.
            if not get_seat_position(seat_id):
                print(
                    f"[feature_commands] seat teleport (bird-eye): seat '{seat_id}' not found"
                )
                return

            if svc.world_state:
                try:
                    svc.world_state.set("cameraViewType", "firstPerson")
                except Exception:
                    pass

            await svc.async_first_person_enter("")
            self._dispatch_seat_teleport(seat_id)
        except Exception as exc:
            print(f"[feature_commands] seat teleport (bird-eye) failed: {exc}")

    def _dispatch_seat_teleport(self, seat_id: str) -> None:
        """Trigger the regular ``seatTeleport`` Events 2.0 handler.

        Avoids duplicating the face-arena yaw + seat-highlight cleanup
        logic that already lives in ``younite.navmesh_route_extension``.
        """
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            parts = seat_id.split("-", 2)
            if len(parts) != 3:
                return
            section, row, seat_num = parts
            dispatch_to_events2(
                "seatTeleport",
                {"section": section, "row": row, "seat": seat_num},
            )
        except Exception as exc:
            print(f"[feature_commands] seat teleport dispatch failed: {exc}")


__all__ = ["SeatDirectionsHandler"]
