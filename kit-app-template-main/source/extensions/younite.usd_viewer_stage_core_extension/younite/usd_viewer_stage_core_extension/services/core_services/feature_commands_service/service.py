"""
Stage-owned feature command handlers (fog/camera/reset/teleport/speed/physics).

Thin orchestrator: wires web events to handlers and exposes the
shared primitives (``dispatch_view_transition_ready``,
``await_navmesh_route_settled``, ``async_first_person_enter``) that
the directions flows depend on.

The major flows live in dedicated submodules:

* :mod:`.view_switcher` — first-person entry + non-FP view transitions
* :mod:`.map_marker_directions` — bird-eye directions panel (POI +
  pin-anywhere)
* :mod:`.seat_directions` — bird-eye seat directions + seat teleport
* :mod:`.fp_state` — first-person state capture / restore
* :mod:`.directions_utils` — pure helpers shared by the directions flows

Smaller handlers (fog, fixed camera, reset, movement speed, camera
height, physics) stay inline because they are small and tightly
coupled to event wiring.
"""
from __future__ import annotations

import asyncio

from .fp_state import FpStateStore
from .map_marker_directions import MapMarkerDirectionsHandler
from .seat_directions import SeatDirectionsHandler
from .view_switcher import ViewSwitcher


class FeatureCommandsService:
    """Stage-owned feature command orchestrator."""

    def __init__(self, *, settings, fog, camera, stage_manager, world_state=None):
        self._settings = settings
        self._fog = fog
        self._camera = camera
        self._stage_manager = stage_manager
        self._world_state = world_state
        self._subs = []
        self._fp_state = FpStateStore(world_state=world_state)
        self._view_switcher = ViewSwitcher(self)
        self._map_marker = MapMarkerDirectionsHandler(self)
        self._seat = SeatDirectionsHandler(self)

    # ------------------------------------------------------------------
    # Accessors used by handler sub-modules
    # ------------------------------------------------------------------

    @property
    def camera(self):
        return self._camera

    @property
    def world_state(self):
        return self._world_state

    @property
    def fp_state(self) -> FpStateStore:
        return self._fp_state

    @property
    def view_switcher(self) -> ViewSwitcher:
        return self._view_switcher

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(name), name
                    )
                except Exception:
                    pass
                try:
                    self._subs.append(
                        ed.observe_event(
                            observer_name=f"younite.usd_viewer_stage_core_extension/{name}",
                            event_name=name,
                            on_event=handler,
                            order=0,
                        )
                    )
                except Exception:
                    pass

            _observe("fogControlRequest", self._on_fog_control)
            _observe(
                "cameraViewSwitchRequest", self._view_switcher.on_camera_view_switch
            )
            _observe(
                "playerStateCaptureRequest",
                self._view_switcher.on_player_state_capture_request,
            )
            _observe("fixedCameraSwitchRequest", self._on_fixed_camera_switch)
            _observe("fixedCameraExitRequest", self._on_fixed_camera_exit)
            _observe("playerEnterXformView", self._on_player_enter_xform_view)
            _observe("playerExitXformView", self._on_player_exit_xform_view)
            _observe("resetStage", self._on_reset_stage)
            _observe("teleportToSpawnpoint", self._view_switcher.on_spawnpoint_teleport)
            _observe("chat.moveToSpawnpoint", self._view_switcher.on_spawnpoint_teleport)
            _observe("chat.moveAccepted", self._view_switcher.on_spawnpoint_teleport)
            _observe("mapMarkerDirectionsStart", self._map_marker.on_start)
            _observe("seatDirectionsStart", self._seat.on_directions_start)
            _observe(
                "seatTeleportFromBirdEye", self._seat.on_teleport_from_bird_eye
            )
            _observe(
                "seatTeleportFromBirdEyeCheck",
                self._seat.on_teleport_from_bird_eye_check,
            )
            _observe(
                "poiTeleportFromBirdEye",
                self._map_marker.on_poi_teleport_from_bird_eye,
            )
            _observe("movementSpeedChange", self._on_movement_speed_change)
            _observe("cameraHeightChange", self._on_camera_height_change)
            _observe("physicsControlRequest", self._on_physics_control_request)
            _observe("mediaContentThemeSet", self._on_media_content_theme_set)
        except Exception:
            pass

        try:
            import carb.settings as cs

            if self._world_state:
                th = self._world_state.get_all().get("mediaContentTheme") or "horseshow"
                cs.get_settings().set("/younite/media/contentTheme", str(th))
        except Exception:
            pass

    def stop(self):
        self._subs.clear()

    # ------------------------------------------------------------------
    # Shared primitives (used by handler sub-modules + internal callers)
    # ------------------------------------------------------------------

    def dispatch_view_transition_ready(
        self,
        view_type: str,
        success: bool,
        error: str = "",
        *,
        spawn_point: str = "",
    ) -> None:
        try:
            import carb.eventdispatcher as _ed

            ed = _ed.get_eventdispatcher()
            payload = {
                "viewType": view_type,
                "result": "success" if success else "error",
                "error": error or "",
            }
            if spawn_point:
                payload["spawnpointName"] = spawn_point
            ed.dispatch_event("viewTransitionReady", payload)
        except Exception:
            pass

    async def await_navmesh_route_settled(
        self,
        route_id: str,
        timeout_sec: float = 20.0,
    ) -> bool:
        """Wait for the next ``navmeshRouteWaypoints`` for ``route_id``.

        Used by the bird-eye → first-person directions flow to keep
        the black view-transition overlay up until the requested route
        is actually drawable (or has failed). Returning here unblocks
        the fade-in: success means the user fades into a scene with
        the route already visible; failure (and timeout) still
        unblocks so the user is never stuck on a black screen — the
        matching ``navmeshRouteError`` / inline panel error will
        surface the failure once they land in first-person.

        Returns ``True`` on a ``success: true`` waypoint event,
        ``False`` otherwise. Transient ``recalculating`` / ``stopped``
        payloads are ignored.
        """
        try:
            import carb
            import carb.eventdispatcher as _ed
            import omni.kit.app as kit_app
        except Exception:
            return False

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        sub_holder: list = []

        def _on_waypoints(evt):
            try:
                from younite.messaging_core_extension.message_utils import (
                    normalize_event_payload,
                )

                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                rid = str(payload.get("routeId") or payload.get("route_id") or "")
                if rid != route_id:
                    return
                success = bool(payload.get("success", True))
                err = str(payload.get("error") or "")
                if not success and err in ("stopped", "recalculating"):
                    return
                if not future.done():
                    loop.call_soon_threadsafe(future.set_result, success)
            except Exception:
                pass

        try:
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("navmeshRouteWaypoints"),
                    "navmeshRouteWaypoints",
                )
            except Exception:
                pass
            ed = _ed.get_eventdispatcher()
            sub = ed.observe_event(
                observer_name=f"younite.usd_viewer_stage_core_extension/await_route_{route_id}",
                event_name="navmeshRouteWaypoints",
                on_event=_on_waypoints,
                order=0,
            )
            sub_holder.append(sub)
        except Exception:
            return False

        try:
            return await asyncio.wait_for(future, timeout=timeout_sec)
        except asyncio.TimeoutError:
            print(
                f"[feature_commands] await_navmesh_route_settled timeout after "
                f"{timeout_sec:.1f}s for route '{route_id}'"
            )
            return False
        finally:
            sub_holder.clear()

    async def async_first_person_enter(
        self,
        spawn_point: str,
        *,
        dispatch_ready: bool = True,
    ) -> bool:
        """Thin forwarder to :meth:`ViewSwitcher.async_first_person_enter`.

        Kept on the orchestrator so the directions handlers can call
        ``svc.async_first_person_enter(...)`` without reaching into
        ``svc.view_switcher.*``.
        """
        return await self._view_switcher.async_first_person_enter(
            spawn_point, dispatch_ready=dispatch_ready
        )

    # ------------------------------------------------------------------
    # Simple event handlers (fog, fixed camera, reset, speed, height, physics)
    # ------------------------------------------------------------------

    def _on_fog_control(self, event):
        try:
            if not self._fog:
                return
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            enabled = bool(payload.get("enabled", True))
            intensity = float(payload.get("intensity", 1.0))
            self._fog.set_fog(enabled=enabled, intensity=intensity)
            if self._world_state:
                self._world_state.set_many(
                    {"fogEnabled": enabled, "fogIntensity": intensity}
                )
        except Exception:
            pass

    def _on_fixed_camera_switch(self, event):
        """Switch viewport to a scene camera (watch-only).

        Payload: ``cameraPrimPath`` or ``cameraId`` (e.g. ``camera_vip_entrance``).
        """
        try:
            if not self._camera:
                return
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            from ..world_conventions import WORLD_ROOT_PATH

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            path = str(payload.get("cameraPrimPath") or "").strip()
            if not path:
                camera_id = str(payload.get("cameraId") or "").strip()
                if camera_id:
                    path = f"{WORLD_ROOT_PATH.rstrip('/')}/{camera_id.lstrip('/')}"
            if path:
                self._camera.switch_to_fixed_camera(path)
        except Exception:
            pass

    def _on_fixed_camera_exit(self, _event):
        """Restore viewport to player camera and re-enable movement."""
        try:
            if not self._camera:
                return
            self._camera.exit_fixed_camera()
        except Exception:
            pass

    def _on_player_enter_xform_view(self, event):
        """Forward to CameraService.enter_xform_view. Payload: ``primPath``."""
        try:
            if not self._camera:
                return
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            prim_path = str(payload.get("primPath") or "").strip()
            if not prim_path:
                return
            self._camera.enter_xform_view(prim_path)
        except Exception:
            pass

    def _on_player_exit_xform_view(self, _event):
        """Forward to CameraService.exit_xform_view."""
        try:
            if not self._camera:
                return
            self._camera.exit_xform_view()
        except Exception:
            pass

    def _on_reset_stage(self, _event):
        try:
            if self._camera:
                if self._camera.is_fixed_camera_active():
                    self._camera.exit_fixed_camera()
                self._camera.reset_camera()
        except Exception:
            pass

    def _on_movement_speed_change(self, event):
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            speed_value = float(payload.get("speed", payload.get("multiplier", 1.0)))

            try:
                if self._settings:
                    self._settings.set(
                        "/younite/player/movementSpeedMultiplier", float(speed_value)
                    )
            except Exception:
                pass

            if self._world_state:
                self._world_state.set("movementSpeed", speed_value)

            try:
                import carb.eventdispatcher as _ed

                _ed.get_eventdispatcher().dispatch_event(
                    "movementSpeedChangeResponse",
                    {"result": "success", "speed": speed_value},
                )
            except Exception:
                pass
        except Exception:
            pass

    def _on_camera_height_change(self, event):
        try:
            # Only apply in first-person view
            try:
                view_type = (
                    self._settings.get("/younite/camera/viewType")
                    if self._settings
                    else None
                )
                if view_type and str(view_type).strip() != "firstPerson":
                    return
            except Exception:
                pass

            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            height_cm = float(payload.get("height", 155))

            import omni.usd
            from pxr import Gf, UsdGeom

            from ..world_conventions import PLAYER_FIRST_PERSON_CAMERA_PATH

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            cam_prim = stage.GetPrimAtPath(PLAYER_FIRST_PERSON_CAMERA_PATH)
            if not cam_prim or not cam_prim.IsValid():
                return

            cam_xf = UsdGeom.Xformable(cam_prim)
            translate_op = cam_xf.GetTranslateOp()
            if translate_op:
                cur = translate_op.Get()
                translate_op.Set(
                    Gf.Vec3d(float(cur[0]), float(height_cm), float(cur[2]))
                )

            if self._world_state:
                self._world_state.set("cameraHeight", height_cm)

            try:
                import carb.eventdispatcher as _ed

                _ed.get_eventdispatcher().dispatch_event(
                    "cameraHeightChangeResponse",
                    {"result": "success", "height": height_cm},
                )
            except Exception:
                pass
        except Exception:
            pass

    def _on_physics_control_request(self, event):
        """Web UI toggle for physics/timeline.

        Payload: ``{ action: "start" | "stop" }``
        """
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            action = str(payload.get("action") or "").strip().lower()
            import omni.timeline

            tl = omni.timeline.get_timeline_interface()
            if not tl:
                return
            if action == "stop":
                try:
                    tl.stop()
                except Exception:
                    pass
            else:
                try:
                    tl.play()
                except Exception:
                    pass
            try:
                if self._settings:
                    self._settings.set(
                        "/app/runLoops/mainLoop/simulationEnabled", action != "stop"
                    )
            except Exception:
                pass
            if self._world_state:
                self._world_state.set(
                    "physicsState", "enabled" if action != "stop" else "disabled"
                )
            try:
                import carb.eventdispatcher as _ed

                _ed.get_eventdispatcher().dispatch_event(
                    "physicsControlResponse",
                    {"result": "success", "action": action},
                )
            except Exception:
                pass
        except Exception:
            pass

    def _on_media_content_theme_set(self, event):
        """Switch active media pack (360° / spatial-sound iconGroup filter)."""
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            theme = str(payload.get("theme") or "horseshow").strip() or "horseshow"

            if self._world_state:
                self._world_state.set("mediaContentTheme", theme)

            try:
                import carb.settings as cs

                cs.get_settings().set("/younite/media/contentTheme", theme)
            except Exception:
                pass
        except Exception:
            pass


__all__ = ["FeatureCommandsService"]
