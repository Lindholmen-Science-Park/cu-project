"""
Map-marker (POI) directions flow from the bird-eye directions panel.

Sequencing wrapper around existing pieces. The directions panel sends
one event with the resolved start spawnpoint and end target; this
handler serialises:

1. Capture stored FP position before ``_async_first_person_enter``
   wipes it — this is what "Current position" means when the user
   has swapped the inputs and chose to navigate back.
2. Enter first-person view (handles LOD switch, navmesh prep, and
   view-transition signalling). Empty ``start_spawn`` falls back to
   stored FP state, mirroring the "back to previous location" button.
3. Compose the route once locally (``RouteComposer.compose``) — only
   to validate routability before teleporting and to compute the body
   yaw for the start rotation. The route engine composes again
   internally; this preview compose is throwaway.
4. Optional teleport to ``start_pos`` (pin-anywhere swap) with the
   player body yaw aligned to the first route segment.
5. Dispatch ``navigationStateSet`` with ``useComposer: true`` and the
   destination world position. The orchestrator's ``_apply_state``
   takes over from here — same pipeline as seat_nav / find-toilets.
   The route engine builds the polyline via ``RouteComposer`` (so we
   still get NavMesh ↔ OSM bridging) and then drives drawing,
   waypoint dispatch, measure, arrival, and pause/play/recalc on the
   exact same lifecycle every other route uses. No bypass, no
   preset injection, no duplicate auto-mover plumbing.
6. Lift the black view-transition overlay once the route has settled.
"""
from __future__ import annotations

import asyncio

from . import directions_utils as dutil


class MapMarkerDirectionsHandler:
    """Orchestrates the bird-eye ``mapMarkerDirectionsStart`` flow."""

    def __init__(self, service):
        self._svc = service

    # ------------------------------------------------------------------
    # Event entrypoint
    # ------------------------------------------------------------------

    def on_start(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            route_id = str(payload.get("routeId") or "poi_nav").strip() or "poi_nav"
            start_spawn = str(payload.get("startSpawnPoint") or "").strip()
            endpoint_path = str(payload.get("endpointPath") or "").strip()
            end_use_stored_fp = bool(payload.get("endUseStoredFp"))

            start_pos = dutil.coerce_vec(payload.get("startPos"))
            end_pos_explicit = dutil.coerce_vec(payload.get("endPos"))
            # Resolve start position from a USD prim's xform when the
            # caller ships `startEndpointPath` instead of explicit
            # `startPos`. Used by the navmesh-POI swap flow: restrooms /
            # quiet zones have no `PlayerSpawnPoint_*` so they can't go
            # through the `startSpawnPoint` path, but they have a prim
            # path we can teleport to exactly like a pin-anywhere
            # `start_pos`. Resolved here (before the async run) so the
            # downstream teleport + route compose uses a single uniform
            # `start_pos` value regardless of how the caller addressed
            # the start point.
            if start_pos is None:
                start_endpoint_path = str(
                    payload.get("startEndpointPath") or ""
                ).strip()
                if start_endpoint_path:
                    resolved = dutil.resolve_prim_path_world(start_endpoint_path)
                    if resolved is not None:
                        start_pos = resolved

            if not endpoint_path and not end_use_stored_fp and not end_pos_explicit:
                return

            asyncio.ensure_future(
                self._run(
                    route_id,
                    start_spawn,
                    endpoint_path,
                    end_use_stored_fp,
                    start_pos,
                    end_pos_explicit,
                )
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Async worker
    # ------------------------------------------------------------------

    async def _run(
        self,
        route_id: str,
        start_spawn: str,
        endpoint_path: str,
        end_use_stored_fp: bool,
        start_pos: "list[float] | None",
        end_pos_explicit: "list[float] | None",
    ) -> None:
        svc = self._svc
        try:
            if svc.world_state:
                try:
                    svc.world_state.set("cameraViewType", "firstPerson")
                except Exception:
                    pass

            # Capture stored FP BEFORE `_async_first_person_enter` consumes
            # and clears it — needed as the route's *end* position in the
            # swap case (``end_use_stored_fp``), mirroring the pattern
            # used in the seat directions flow. Without this the handler
            # silently returns (end_world=None) because the FP store is
            # empty by the time we try to read it below.
            stored_fp_pos: "list[float] | None" = None
            stored_pre = svc.fp_state.read()
            if stored_pre:
                pos_pre = stored_pre.get("pos") or (0.0, 0.0, 0.0)
                stored_fp_pos = [
                    float(pos_pre[0]),
                    float(pos_pre[1]),
                    float(pos_pre[2]),
                ]

            # Defer the `viewTransitionReady` signal — the black overlay
            # must stay up until the route below has actually been
            # composed, so the user fades into a scene with the path
            # visible. On failure we still dispatch ready below so the
            # user never gets stuck on a black screen.
            fp_ok = await svc.async_first_person_enter(
                start_spawn, dispatch_ready=False
            )
            if not fp_ok:
                return

            end_world = self._resolve_end_world(
                endpoint_path=endpoint_path,
                end_use_stored_fp=end_use_stored_fp,
                end_pos_explicit=end_pos_explicit,
                stored_fp_pos=stored_fp_pos,
            )
            if end_world is None:
                svc.dispatch_view_transition_ready(
                    "firstPerson",
                    True,
                    "",
                    spawn_point=start_spawn or "",
                )
                return

            # Resolve the intended start world position. For the pin-
            # anywhere swap case, this is ``start_pos`` — the player
            # will be teleported there below. Otherwise, it's the
            # player's current world position (post FP-enter).
            if start_pos is not None:
                start_world = [
                    float(start_pos[0]),
                    float(start_pos[1]),
                    float(start_pos[2]),
                ]
            else:
                start_world = dutil.get_player_world_pos()
            if start_world is None:
                svc.dispatch_view_transition_ready(
                    "firstPerson",
                    False,
                    "player position unavailable",
                    spawn_point=start_spawn or "",
                )
                return

            # Preview compose — only used to (a) fail fast with the
            # no-route error overlay before teleporting the player and
            # (b) derive the body yaw for the start rotation. The route
            # engine will compose again internally from the same
            # start/end via ``useComposer=True`` below; that engine
            # compose is the authoritative polyline that drives auto-
            # move, draw, measure, and recompute-on-pause. No risk of
            # the two diverging because the engine's first compute uses
            # the player's *post-teleport* position as the start.
            composed = dutil.compose_route(start_world, end_world)
            if composed is None or len(composed.polyline) < 2:
                self._report_no_route(
                    route_id=route_id,
                    start_world=start_world,
                    end_world=end_world,
                    start_spawn=start_spawn,
                )
                return

            initial_yaw_deg = dutil.yaw_from_polyline(
                [list(p) for p in composed.polyline]
            )

            self._apply_start_rotation(
                start_pos=start_pos,
                initial_yaw_deg=initial_yaw_deg,
            )

            # Hand off to the orchestrator-driven route pipeline. From
            # here on the route lives on the *exact* same lifecycle as
            # seat_nav / find-toilets / search-POI:
            #
            #   navigationStateSet (here)
            #     → orchestrator._apply_state
            #     → navmeshRouteCalculate (autoMove=False)
            #     → set_route_for_id(use_composer=True)
            #     → RouteComposer builds polyline (NavMesh + OSM)
            #     → navmeshRouteWaypoints (faceDirection=True, speeds)
            #     → auto-mover caches waypoints, awaits Play
            #
            # Play / Pause then flips ``autoMove`` via another
            # navigationStateSet, which re-enters _apply_state and
            # re-dispatches navmeshRouteCalculate — same recalc that
            # seat_nav uses for pause+free-walk re-routing. There is no
            # second code path for bird-eye routes.
            try:
                from younite.messaging_core_extension.message_utils import (
                    dispatch_to_events2,
                )

                dispatch_to_events2(
                    "navigationStateSet",
                    {
                        "movementMode": "pointClick",
                        "autoMove": False,
                        "routeId": route_id,
                        "endPos": [
                            float(end_world[0]),
                            float(end_world[1]),
                            float(end_world[2]),
                        ],
                        "useComposer": True,
                        "drawPath": True,
                    },
                )
            except Exception as exc:
                print(
                    f"[feature_commands] navigationStateSet dispatch failed: {exc}"
                )

            # Hold the black view-transition overlay until the route
            # engine has actually emitted the first waypoints — same
            # pattern seat_directions uses. Without this the user would
            # fade into the scene before the spheres draw and see an
            # empty FAB / dead Play button while compose is still
            # running.
            try:
                await svc.await_navmesh_route_settled(route_id)
            except Exception:
                pass
            svc.dispatch_view_transition_ready(
                "firstPerson",
                True,
                "",
                spawn_point=start_spawn or "",
            )
        except Exception as exc:
            print(f"[feature_commands] map-marker directions start failed: {exc}")
            svc.dispatch_view_transition_ready(
                "firstPerson",
                False,
                str(exc),
                spawn_point=start_spawn or "",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_end_world(
        self,
        *,
        endpoint_path: str,
        end_use_stored_fp: bool,
        end_pos_explicit: "list[float] | None",
        stored_fp_pos: "list[float] | None",
    ) -> "list[float] | None":
        """Resolve the route end world position by precedence.

        Precedence:
          1. Explicit ``endPos`` (pin-anywhere forward flow).
          2. Stored FP snapshot (swap cases — we've teleported to
             ``start_pos``, route walks back to the user's previous FP
             location). We use the pre-captured snapshot because
             fp_enter wiped the on-disk store.
          3. ``endpointPath`` (classic POI flow).
        """
        if end_pos_explicit is not None:
            return list(end_pos_explicit)
        if end_use_stored_fp:
            if stored_fp_pos is not None:
                return list(stored_fp_pos)
            return None
        if endpoint_path:
            return dutil.resolve_prim_path_world(endpoint_path)
        return None

    def _report_no_route(
        self,
        *,
        route_id: str,
        start_world,
        end_world,
        start_spawn: str,
    ) -> None:
        """Tell the web side explicitly when the composer cannot build a path.

        Mirrors the city-navigate flow which prints "No path found" and
        surfaces it in the UI. Without this the directions panel would
        silently drop the user at the FP spawn with no route drawn.
        """
        svc = self._svc
        print(
            "[feature_commands] directions compose failed — no walkable route "
            f"from {start_world} to {end_world}"
        )
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            dispatch_to_events2(
                "navmeshRouteError",
                {
                    "routeId": route_id,
                    "error": (
                        "no walkable route — endpoint may be in a "
                        "disconnected OSM area"
                    ),
                },
            )
            dispatch_to_events2(
                "navmeshRouteMeasure",
                {
                    "routeId": route_id,
                    "success": False,
                    "error": "no walkable route",
                    "distanceMetersBase": 0.0,
                    "estimatedTimeSecondsBase": 0.0,
                },
            )
        except Exception as exc:
            print(f"[feature_commands] route-error dispatch failed: {exc}")
        svc.dispatch_view_transition_ready(
            "firstPerson",
            True,
            "",
            spawn_point=start_spawn or "",
        )

    def _apply_start_rotation(
        self,
        *,
        start_pos: "list[float] | None",
        initial_yaw_deg: "float | None",
    ) -> None:
        """Apply path-aligned yaw, either via a pin-anywhere teleport or in-place.

        For the pin-anywhere swap case, teleport the player to the pin
        with the path-aligned yaw *as a world-space body rotation* —
        ``camera_local_yaw_deg`` would stack on top of the spawn body
        yaw (some spawns are authored with -144° etc.) and leave the
        view pointing the wrong way. ``world_body_yaw_deg`` zeroes the
        camera local and sets the body yaw directly, so the user's
        view axis equals the path axis after the teleport regardless
        of which spawn FP-enter seeded from.

        For the non-swap case (player already at FP spawn), the body
        yaw was set by FP-enter to match the spawn; we need to rotate
        the *body* to match the path the same way.
        """
        svc = self._svc
        ts = (
            getattr(svc.camera, "_teleport_service", None)
            if svc.camera
            else None
        )
        if start_pos is not None:
            try:
                if ts:
                    ts.teleport_to_coordinates(
                        float(start_pos[0]),
                        float(start_pos[1]),
                        float(start_pos[2]),
                        world_body_yaw_deg=initial_yaw_deg,
                    )
            except Exception as exc:
                print(f"[feature_commands] pin start_pos teleport failed: {exc}")
        elif initial_yaw_deg is not None:
            # Player is already where they need to be — just rotate
            # the body to face the path. We write the player's
            # ``rotateXYZ`` directly and reset the camera local + the
            # input controller's cached yaw so the three stay in sync.
            # (Just dispatching ``immediateViewAngles`` with the world
            # yaw doesn't work: it sets camera local, which stacks on
            # the non-zero body yaw from the spawn.)
            try:
                import omni.usd
                from pxr import Gf, UsdGeom

                stage = omni.usd.get_context().get_stage()
                if stage:
                    player_prim = stage.GetPrimAtPath("/World/PlayerCharacter")
                    if player_prim and player_prim.IsValid():
                        pxf = UsdGeom.Xformable(player_prim)
                        prot = pxf.GetRotateXYZOp() or pxf.AddRotateXYZOp()
                        prot.Set(Gf.Vec3d(0.0, float(initial_yaw_deg), 0.0))
                        cam_prim = stage.GetPrimAtPath(
                            "/World/PlayerCharacter/first_person_camera"
                        )
                        if cam_prim and cam_prim.IsValid():
                            cxf = UsdGeom.Xformable(cam_prim)
                            crot = cxf.GetRotateXYZOp() or cxf.AddRotateXYZOp()
                            crot.Set(Gf.Vec3d(0.0, 0.0, 0.0))
                from younite.messaging_core_extension.message_utils import (
                    dispatch_to_events2,
                )

                dispatch_to_events2(
                    "younite.player.immediateViewAngles",
                    {"yaw": 0.0, "pitch": 0.0},
                )
            except Exception as exc:
                print(f"[feature_commands] body yaw rotate failed: {exc}")

    # ------------------------------------------------------------------
    # POI teleport (from bird-eye)
    # ------------------------------------------------------------------
    #
    # Plain ``poiTeleport`` (navmesh_route_extension) only moves the player.
    # From bird-eye that leaves the overhead camera and light LOD active.
    # Mirror ``SeatDirectionsHandler.on_teleport_from_bird_eye``: enter
    # first-person (view + LOD + navmesh prep), then dispatch ``poiTeleport``.

    def on_poi_teleport_from_bird_eye(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            prim_path = str(payload.get("primPath") or payload.get("prim_path") or "").strip()
            if not prim_path:
                return
            asyncio.ensure_future(self._run_poi_teleport_from_bird_eye(prim_path))
        except Exception:
            pass

    async def _run_poi_teleport_from_bird_eye(self, prim_path: str) -> None:
        svc = self._svc
        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                raise RuntimeError("No USD stage")
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                print(
                    f"[feature_commands] POI teleport (bird-eye): prim not found: {prim_path}"
                )
                svc.dispatch_view_transition_ready(
                    "firstPerson",
                    False,
                    f"prim not found: {prim_path}",
                )
                return

            if svc.world_state:
                try:
                    svc.world_state.set("cameraViewType", "firstPerson")
                except Exception:
                    pass

            # Keep the black overlay until ``poiTeleport`` finishes and
            # ``poi_routes`` dispatches ``viewTransitionReady`` after settle
            # (same deferral as ``mapMarkerDirectionsStart``).
            fp_ok = await svc.async_first_person_enter("", dispatch_ready=False)
            if not fp_ok:
                return

            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            dispatch_to_events2("poiTeleport", {"primPath": prim_path})
        except Exception as exc:
            print(f"[feature_commands] POI teleport (bird-eye) failed: {exc}")
            svc.dispatch_view_transition_ready("firstPerson", False, str(exc))


__all__ = ["MapMarkerDirectionsHandler"]
