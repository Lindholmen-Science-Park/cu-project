import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .ease_helpers import ease_scale_remaining, smootherstep01



@dataclass
class NavigationState:
    # Manual input mode (WASD/joystick are handled by PlayerInputController).
    # Default is pointClick (lightweight, no PhysX CCT). WASD activates CCT on demand.
    movement_mode: str = "pointClick"  # "wasd" | "mobileJoystick" | "pointClick" | "disabled"

    # Navigation/path planning
    navigation_enabled: bool = True
    draw_path: bool = False

    # Auto-move (player): follow navmesh shortest route waypoints when available.
    # Default True for point-and-click mode.
    auto_move: bool = True

    # Target / references
    route_id: str = "player"
    startpoint_path: Optional[str] = None
    endpoint_path: Optional[str] = None
    start_pos: Optional[Tuple[float, float, float]] = None
    end_pos: Optional[Tuple[float, float, float]] = None

    # Optional costs
    camera_area_costs: Optional[Dict[str, float]] = None

    # When True, the navmesh_route extension routes via the
    # ``RouteComposer`` (NavMesh ↔ OSM bridges) instead of raw NavMesh
    # only. Used by the bird-eye directions panel (``poi_nav``) so the
    # same orchestrator-driven pipeline as seat_nav / find-toilets
    # handles cross-island navigation.
    use_composer: bool = False

    # Diagnostics
    last_updated_ms: int = field(default_factory=lambda: int(time.time() * 1000))


class NavigationOrchestratorService:
    """
    PlayerCore-owned orchestrator that merges UI/device state into:
    - manual input enable/disable
    - navmesh route calculation/visualization requests (routeId-scoped)
    - player auto-move for point&click (via PointClickAutoMover)

    It is readiness-gated: it will not act until PlayerCore reports ready.
    """

    FACE_LOOK_AHEAD_DIST: float = 800.0
    # Default / fallback face-turn (other callers)
    FACE_TURN_RATE: float = 175.0
    FACE_TURN_DONE_THRESHOLD: float = 0.5
    FACE_TURN_EASE_ZONE_DEG: float = 44.0
    FACE_TURN_EASE_MIN_SCALE: float = 0.34
    FACE_TURN_ZONE_CAP_FRACTION: float = 0.5
    # Gentler profile: first waypoint with faceDirection (seat_nav, exits, POI, …)
    FACE_ROUTE_TURN_RATE: float = 132.0
    FACE_ROUTE_DONE_THRESHOLD: float = 0.4
    FACE_ROUTE_EASE_ZONE_DEG: float = 62.0
    FACE_ROUTE_EASE_MIN_SCALE: float = 0.18
    FACE_ROUTE_ZONE_CAP_FRACTION: float = 0.62
    # Seat arrival / playerFaceWorldXZ — smootherstep position S-curve (no rate×ease plateau)
    FACE_STADIUM_DONE_THRESHOLD: float = 0.35
    FACE_STADIUM_AVG_DEG_PER_S: float = 74.0   # mean speed; peak ~1.875× this on smootherstep
    FACE_STADIUM_DURATION_MIN_S: float = 0.45
    FACE_STADIUM_DURATION_MAX_S: float = 1.65

    def __init__(
        self,
        *,
        movement_controller=None,
        auto_mover=None,
        mode_change_callback=None,
        get_player_path: Optional[Callable[[], str]] = None,
        get_camera_path: Optional[Callable[[], str]] = None,
    ):
        self._movement_controller = movement_controller
        self._auto_mover = auto_mover
        self._mode_change_callback = mode_change_callback
        self._get_player_path = get_player_path or (lambda: "/World/PlayerCharacter")
        self._get_camera_path = get_camera_path or (lambda: "/World/PlayerCharacter/first_person_camera")
        self._subs = []
        self._player_ready = False
        self._state = NavigationState()
        self._face_turn_target: Optional[float] = None
        self._face_turn_sub: Optional[Any] = None
        self._face_turn_initial_remaining: float = 0.0
        self._face_turn_profile: str = "default"
        self._face_turn_start_yaw: float = 0.0
        self._face_turn_total_delta: float = 0.0
        self._face_turn_elapsed_s: float = 0.0
        self._face_turn_duration_s: float = 1.0

    def get_manual_input_enabled(self) -> bool:
        """Whether input processing should be enabled.

        Returns False only for "disabled" mode.  Camera look (touch/mouse)
        needs to work in all other modes including pointClick.  WASD/joystick
        movement gating is handled in _on_movement_update, not here.
        """
        try:
            return bool(self._state.movement_mode != "disabled")
        except Exception:
            return True

    def start(self) -> None:
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                try:
                    self._subs.append(
                        ed.observe_event(
                            observer_name=f"younite.usd_viewer_player_core_extension/{name}",
                            event_name=name,
                            on_event=handler,
                            order=0,
                        )
                    )
                except Exception:
                    pass

            def _on_player_ready(evt):
                _payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._player_ready = bool(_payload.get("success", True))
                self._apply_state()

            def _on_nav_state_set(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._merge_state_from_payload(payload)
                try:
                    if self._auto_mover and hasattr(self._auto_mover, "on_navigation_state"):
                        self._auto_mover.on_navigation_state(payload)
                except Exception:
                    pass
                self._apply_state()

            def _ensure_auto_move(self_ref=self):
                """Re-enable auto_move on both orchestrator state and auto-mover.
                Clicking on the world implies the user wants to move there."""
                s = self_ref._state
                if not s.auto_move:
                    s.auto_move = True
                    try:
                        if self_ref._auto_mover and hasattr(self_ref._auto_mover, "on_navigation_state"):
                            self_ref._auto_mover.on_navigation_state({"autoMove": True})
                    except Exception:
                        pass
                if s.route_id != "player":
                    old_route_id = s.route_id
                    s.route_id = "player"
                    # Point-click player hops always use raw NavMesh —
                    # the composer flag belongs to the previous user
                    # route (poi_nav etc.) and would force a useless
                    # OSM compose for an in-Scandinavium ground click.
                    s.use_composer = False
                    # Same reasoning for ``draw_path``: precalculated
                    # routes (poi_nav / seat_nav / find_toilets / quiet
                    # zone) ship with ``drawPath: true`` so their sphere
                    # trail renders. Point-click player hops must not
                    # inherit it — otherwise the spheres reappear on
                    # every ground click after the user has interacted
                    # with one of those routes (most visible after a
                    # bird-eye "Start navigation" → land in FP → click).
                    s.draw_path = False
                    try:
                        if self_ref._auto_mover and hasattr(self_ref._auto_mover, "on_navigation_state"):
                            self_ref._auto_mover.on_navigation_state({"routeId": "player"})
                    except Exception:
                        pass
                    # Notify that the previous POI auto-move was interrupted by a
                    # ground click.  The route extension will clear _auto_move_active
                    # and recalc; the web UI will pause (show play button, keep route
                    # visible with 5 s recalc) without overriding the new player route.
                    try:
                        from younite.messaging_core_extension.message_utils import dispatch_to_events2
                        dispatch_to_events2("autoMoveStatus", {
                            "routeId": old_route_id,
                            "active": False,
                            "reason": "interrupted",
                        })
                    except Exception:
                        pass

            def _on_pick_response(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                intent = str(payload.get("intent") or "")
                if intent != "navigation.pointClick":
                    return
                hit = payload.get("hit") or {}
                world = hit.get("world") if isinstance(hit, dict) else None
                if not (isinstance(world, dict) and world):
                    return
                try:
                    self._state.end_pos = (float(world.get("x")), float(world.get("y")), float(world.get("z")))
                    self._state.endpoint_path = None
                    self._state.last_updated_ms = int(time.time() * 1000)
                except Exception:
                    return
                _ensure_auto_move()
                self._apply_state()

            def _on_navigation_request_point(evt):
                # New contract: interactions extension emits this only when no clickable matched.
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                world = payload.get("world") if isinstance(payload, dict) else None
                if not (isinstance(world, dict) and world):
                    return
                try:
                    self._state.end_pos = (float(world.get("x")), float(world.get("y")), float(world.get("z")))
                    self._state.endpoint_path = None
                    self._state.last_updated_ms = int(time.time() * 1000)
                except Exception:
                    return
                _ensure_auto_move()
                self._apply_state()

            def _on_waypoints(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                try:
                    if self._auto_mover and hasattr(self._auto_mover, "on_route_waypoints"):
                        self._auto_mover.on_route_waypoints(payload)
                except Exception:
                    pass
                if payload.get("faceDirection") and payload.get("success"):
                    # Guided routes (seat_nav, restrooms, POI directions, etc.)
                    # need this initial face-before-walk. Generic ground
                    # point-click uses auto-mover look-ahead only (no
                    # faceDirection on the player route).
                    try:
                        self._face_route_direction(payload)
                    except Exception:
                        pass

            def _on_face_world_xz(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                try:
                    tx = float(payload.get("x"))
                    tz = float(payload.get("z"))
                except (TypeError, ValueError):
                    return
                self.face_toward_world_xz(tx, tz)

            _observe("younite.player.ready", _on_player_ready)
            _observe("navigationStateSet", _on_nav_state_set)
            # Prefer navigation.requestPoint (deterministic click routing). Keep legacy pick.response handler too.
            _observe("younite.navigation.requestPoint", _on_navigation_request_point)
            _observe("younite.pick.response", _on_pick_response)
            _observe("navmeshRouteWaypoints", _on_waypoints)
            _observe("playerFaceWorldXZ", _on_face_world_xz)
        except Exception as e:
            print(f"[player_core] navigation orchestrator start failed: {e}")

    def is_face_turn_active(self) -> bool:
        """True while orchestrator-owned smooth yaw is running (auto-mover should defer)."""
        return self._face_turn_target is not None

    def stop_face_turn_if_active(self) -> None:
        """Cancel in-progress smooth yaw (e.g. after teleport set facing synchronously)."""
        self._stop_face_turn()

    def stop(self) -> None:
        self._stop_face_turn()
        self._subs.clear()

    def _merge_state_from_payload(self, payload: Dict[str, Any]) -> None:
        s = self._state
        try:
            if "movementMode" in payload:
                old_mode = s.movement_mode
                s.movement_mode = str(payload.get("movementMode") or s.movement_mode)
                # Notify extension about mode change so it can activate/deactivate CCT
                if s.movement_mode != old_mode and self._mode_change_callback:
                    try:
                        self._mode_change_callback(s.movement_mode)
                    except Exception as e:
                        print(f"[player_core] mode_change_callback error: {e}")
            if "navigationEnabled" in payload:
                s.navigation_enabled = bool(payload.get("navigationEnabled"))
            if "drawPath" in payload:
                s.draw_path = bool(payload.get("drawPath"))
            if "autoMove" in payload:
                s.auto_move = bool(payload.get("autoMove"))
            if "routeId" in payload:
                rid = str(payload.get("routeId") or "").strip()
                if rid:
                    old_rid = s.route_id
                    s.route_id = rid
                    # Partial payloads only update keys they carry. Handing off from
                    # bird-eye / POI / seat routes leaves drawPath+useComposer True
                    # unless explicitly cleared — point-click player hops must not
                    # inherit (spheres on every NavMesh click; spurious OSM compose).
                    if rid in ("player", "default") and old_rid not in ("player", "default"):
                        if "drawPath" not in payload:
                            s.draw_path = False
                        if "useComposer" not in payload:
                            s.use_composer = False

            if "startpointPath" in payload:
                s.startpoint_path = str(payload.get("startpointPath") or "") or None
                if s.startpoint_path:
                    s.start_pos = None
            if "endpointPath" in payload:
                s.endpoint_path = str(payload.get("endpointPath") or "") or None
                if s.endpoint_path:
                    s.end_pos = None

            def _parse_vec3(v):
                if isinstance(v, (list, tuple)) and len(v) >= 3:
                    return (float(v[0]), float(v[1]), float(v[2]))
                if isinstance(v, dict):
                    x = v.get("x", v.get("X"))
                    y = v.get("y", v.get("Y"))
                    z = v.get("z", v.get("Z"))
                    if x is not None and y is not None and z is not None:
                        return (float(x), float(y), float(z))
                return None

            if "startPos" in payload:
                s.start_pos = _parse_vec3(payload.get("startPos"))
                if s.start_pos is not None:
                    s.startpoint_path = None
            if "endPos" in payload:
                s.end_pos = _parse_vec3(payload.get("endPos"))
                if s.end_pos is not None:
                    s.endpoint_path = None

            if "cameraAreaCosts" in payload and isinstance(payload.get("cameraAreaCosts"), dict):
                s.camera_area_costs = dict(payload.get("cameraAreaCosts") or {})

            if "useComposer" in payload:
                s.use_composer = bool(payload.get("useComposer"))

            # Enforce: player autoMove is only meaningful in pointClick mode.
            if s.movement_mode != "pointClick":
                s.auto_move = False

            s.last_updated_ms = int(time.time() * 1000)
        except Exception:
            pass

    def _apply_state(self) -> None:
        if not self._player_ready:
            return

        # Manual input enable/disable
        try:
            if self._movement_controller and hasattr(self._movement_controller, "set_input_enabled"):
                # Only force-disable input here. Enabling is handled by the per-frame loop so that
                # auto-move (point&click) can temporarily disable manual input without fighting this service.
                if self._state.movement_mode == "disabled":
                    self._movement_controller.set_input_enabled(False)
        except Exception:
            pass

        # Dispatch route calculation (or stop) based on state.
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            rid = self._state.route_id or "player"

            if not self._state.navigation_enabled:
                dispatch_to_events2("navmeshRouteStop", {"routeId": rid})
                return

            start_ref = None
            if self._state.start_pos is not None:
                start_ref = self._state.start_pos
            elif self._state.startpoint_path:
                start_ref = self._state.startpoint_path
            else:
                start_ref = "/World/PlayerCharacter"

            end_ref = None
            if self._state.end_pos is not None:
                end_ref = self._state.end_pos
            elif self._state.endpoint_path:
                end_ref = self._state.endpoint_path

            if end_ref is None:
                return

            is_player_route = rid in ("player", "default")
            enable_periodic_recalc = True
            if is_player_route and (self._state.movement_mode == "pointClick" or isinstance(end_ref, tuple)):
                enable_periodic_recalc = False

            draw_payload = bool(self._state.draw_path) if is_player_route else True
            payload: Dict[str, Any] = {
                "routeId": rid,
                "drawPath": draw_payload,
                "enablePeriodicRecalc": bool(enable_periodic_recalc),
                "startUseGround": True,
                "autoMove": bool(self._state.auto_move),
            }
            if isinstance(start_ref, tuple):
                payload["startPos"] = [start_ref[0], start_ref[1], start_ref[2]]
            else:
                payload["startpointPath"] = str(start_ref)

            if isinstance(end_ref, tuple):
                payload["endPos"] = [end_ref[0], end_ref[1], end_ref[2]]
            else:
                payload["endpointPath"] = str(end_ref)

            if isinstance(self._state.camera_area_costs, dict):
                payload["cameraAreaCosts"] = dict(self._state.camera_area_costs)

            if self._state.use_composer:
                payload["useComposer"] = True

            dispatch_to_events2("navmeshRouteCalculate", payload)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Face route direction on initial calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _look_ahead_point(
        points: List[List[float]],
        budget: float,
    ) -> Optional[Tuple[float, float, float]]:
        """Walk *budget* stage-units along the polyline and return the reached point."""
        if len(points) < 2:
            return None
        prev = points[0]
        target = points[1]
        for p in points[1:]:
            dx = p[0] - prev[0]
            dz = p[2] - prev[2]
            seg_len = math.sqrt(dx * dx + dz * dz)
            if seg_len < 1e-6:
                prev = p
                continue
            if budget <= seg_len:
                t = budget / seg_len
                return (prev[0] + dx * t, prev[1], prev[2] + dz * t)
            budget -= seg_len
            prev = p
            target = p
        return (target[0], target[1], target[2])

    def face_toward_world_xz(self, target_x: float, target_z: float) -> None:
        """Smoothly yaw the first-person camera to face a world XZ point (e.g. bowl center)."""
        try:
            import omni.usd
            from pxr import UsdGeom, Usd, Gf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            player_path = self._get_player_path()
            player_prim = stage.GetPrimAtPath(str(player_path))
            if not (player_prim and player_prim.IsValid()):
                return

            xf = UsdGeom.Xformable(player_prim)
            m = xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            if hasattr(m, "ExtractTranslation"):
                pos = m.ExtractTranslation()
            else:
                pos = Gf.Vec3d(m[3][0], m[3][1], m[3][2])
            px, pz = float(pos[0]), float(pos[2])
            dx = float(target_x) - px
            dz = float(target_z) - pz
            if dx * dx + dz * dz < 1e-6:
                return

            world_yaw = math.degrees(math.atan2(-dx, -dz))

            parent_yaw = 0.0
            p_xf = UsdGeom.Xformable(player_prim)
            rot_op = p_xf.GetRotateXYZOp()
            if rot_op and rot_op.Get():
                parent_yaw = float(rot_op.Get()[1])
            else:
                rot_op = p_xf.GetRotateYXZOp()
                if rot_op and rot_op.Get():
                    parent_yaw = float(rot_op.Get()[0])

            target_yaw = world_yaw - parent_yaw
            self._start_face_turn(target_yaw, profile="stadium")
        except Exception:
            pass

    def _face_route_direction(self, payload: Dict[str, Any]) -> None:
        """Rotate the camera to face the direction of a newly calculated route (eased)."""
        points = payload.get("points")
        if not isinstance(points, list) or len(points) < 2:
            return

        start = points[0]
        la = self._look_ahead_point(points, self.FACE_LOOK_AHEAD_DIST)
        if la is None:
            return

        dx = la[0] - start[0]
        dz = la[2] - start[2]
        if (dx * dx + dz * dz) < 1e-6:
            return

        world_yaw = math.degrees(math.atan2(-dx, -dz))

        try:
            import omni.usd
            from pxr import UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            player_path = self._get_player_path()
            player_prim = stage.GetPrimAtPath(str(player_path))
            if not (player_prim and player_prim.IsValid()):
                return

            parent_yaw = 0.0
            p_xf = UsdGeom.Xformable(player_prim)
            rot_op = p_xf.GetRotateXYZOp()
            if rot_op and rot_op.Get():
                parent_yaw = float(rot_op.Get()[1])
            else:
                rot_op = p_xf.GetRotateYXZOp()
                if rot_op and rot_op.Get():
                    parent_yaw = float(rot_op.Get()[0])

            target_yaw = world_yaw - parent_yaw
            self._start_face_turn(target_yaw, profile="route")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Smooth face-turn helpers
    # ------------------------------------------------------------------

    def _capture_face_turn_span(self, target_yaw: float) -> None:
        """Store initial angular span for ease-in/out on the face-turn."""
        try:
            import omni.usd
            from pxr import UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                self._face_turn_initial_remaining = 180.0
                return
            cam_path = self._get_camera_path()
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if not (cam_prim and cam_prim.IsValid()):
                self._face_turn_initial_remaining = 180.0
                return
            cam_xf = UsdGeom.Xformable(cam_prim)
            cam_rot = cam_xf.GetRotateXYZOp() or cam_xf.AddRotateXYZOp()
            cur_rot = cam_rot.Get()
            cur_yaw = float(cur_rot[1]) if cur_rot else 0.0
            delta = (float(target_yaw) - cur_yaw + 180.0) % 360.0 - 180.0
            self._face_turn_start_yaw = float(cur_yaw)
            self._face_turn_total_delta = float(delta)
            self._face_turn_initial_remaining = max(abs(float(delta)), 1.0)
            if self._face_turn_profile == "stadium":
                span = abs(float(delta))
                dur = span / max(self.FACE_STADIUM_AVG_DEG_PER_S, 1.0)
                dur = max(
                    self.FACE_STADIUM_DURATION_MIN_S,
                    min(self.FACE_STADIUM_DURATION_MAX_S, dur),
                )
                self._face_turn_duration_s = float(dur)
                self._face_turn_elapsed_s = 0.0
        except Exception:
            self._face_turn_initial_remaining = 180.0
            self._face_turn_duration_s = 1.0
            self._face_turn_elapsed_s = 0.0

    def _face_turn_tuning(self) -> Dict[str, float]:
        profile = self._face_turn_profile
        if profile == "route":
            return {
                "rate": self.FACE_ROUTE_TURN_RATE,
                "done": self.FACE_ROUTE_DONE_THRESHOLD,
                "zone": self.FACE_ROUTE_EASE_ZONE_DEG,
                "min_scale": self.FACE_ROUTE_EASE_MIN_SCALE,
                "zone_cap": self.FACE_ROUTE_ZONE_CAP_FRACTION,
            }
        if profile == "stadium":
            return {"done": self.FACE_STADIUM_DONE_THRESHOLD}
        return {
            "rate": self.FACE_TURN_RATE,
            "done": self.FACE_TURN_DONE_THRESHOLD,
            "zone": self.FACE_TURN_EASE_ZONE_DEG,
            "min_scale": self.FACE_TURN_EASE_MIN_SCALE,
            "zone_cap": self.FACE_TURN_ZONE_CAP_FRACTION,
        }

    def _start_face_turn(self, target_yaw: float, *, profile: str = "default") -> None:
        """Begin (or retarget) a smooth camera rotation toward *target_yaw*."""
        self._face_turn_profile = profile if profile in ("route", "stadium") else "default"
        self._face_turn_target = target_yaw
        self._capture_face_turn_span(target_yaw)
        if self._face_turn_sub is not None:
            return
        try:
            import carb.eventdispatcher
            import omni.kit.app

            self._face_turn_sub = carb.eventdispatcher.get_eventdispatcher().observe_event(
                observer_name="younite.usd_viewer_player_core_extension/face_turn",
                event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
                on_event=self._on_face_turn_update,
                order=0,
            )
        except Exception:
            self._apply_yaw_instant(target_yaw)
            self._face_turn_target = None

    def _stop_face_turn(self) -> None:
        self._face_turn_target = None
        self._face_turn_sub = None
        self._face_turn_initial_remaining = 0.0
        self._face_turn_profile = "default"
        self._face_turn_elapsed_s = 0.0

    def _apply_yaw_instant(self, yaw: float) -> None:
        """Fallback: set camera yaw and sync movement controller in one shot."""
        try:
            import omni.usd
            from pxr import UsdGeom, Gf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            cam_path = self._get_camera_path()
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if cam_prim and cam_prim.IsValid():
                cam_xf = UsdGeom.Xformable(cam_prim)
                cam_rot = cam_xf.GetRotateXYZOp() or cam_xf.AddRotateXYZOp()
                cur_rot = cam_rot.Get() or Gf.Vec3d(0.0, 0.0, 0.0)
                cam_rot.Set(Gf.Vec3d(float(cur_rot[0]), float(yaw), 0.0))
            if self._movement_controller and hasattr(self._movement_controller, "set_view_angles"):
                cur_pitch = 0.0
                try:
                    _, cur_pitch = self._movement_controller.get_view_angles()
                except Exception:
                    pass
                self._movement_controller.set_view_angles(float(yaw), cur_pitch)
        except Exception:
            pass

    def _on_face_turn_update(self, event) -> None:
        """Per-frame callback: rate-limited rotation toward *_face_turn_target*."""
        target = self._face_turn_target
        if target is None:
            self._stop_face_turn()
            return
        try:
            dt = 0.0
            try:
                payload = getattr(event, "payload", None) or {}
                if isinstance(payload, dict):
                    dt = float(payload.get("dt", 0.0))
            except Exception:
                dt = 0.0
            if dt <= 0.0:
                dt = 1.0 / 60.0

            import omni.usd
            from pxr import UsdGeom, Gf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                self._stop_face_turn()
                return

            cam_path = self._get_camera_path()
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if not (cam_prim and cam_prim.IsValid()):
                self._stop_face_turn()
                return

            cam_xf = UsdGeom.Xformable(cam_prim)
            cam_rot = cam_xf.GetRotateXYZOp() or cam_xf.AddRotateXYZOp()
            cur_rot = cam_rot.Get() or Gf.Vec3d(0.0, 0.0, 0.0)
            cur_yaw = float(cur_rot[1])

            delta = (target - cur_yaw + 180.0) % 360.0 - 180.0
            tuning = self._face_turn_tuning()
            done_threshold = float(tuning["done"])

            if abs(delta) <= done_threshold:
                cam_rot.Set(Gf.Vec3d(float(cur_rot[0]), float(target), 0.0))
                self._sync_controller_yaw(target)
                self._stop_face_turn()
                return

            if self._face_turn_profile == "stadium":
                self._face_turn_elapsed_s += float(dt)
                dur = max(self._face_turn_duration_s, 1e-6)
                t_lin = min(1.0, self._face_turn_elapsed_s / dur)
                t_eased = smootherstep01(t_lin)
                new_yaw = self._face_turn_start_yaw + self._face_turn_total_delta * t_eased
                if t_lin >= 1.0:
                    new_yaw = float(target)
            else:
                ease_scale = ease_scale_remaining(
                    abs(delta),
                    self._face_turn_initial_remaining,
                    zone=tuning["zone"],
                    min_scale=tuning["min_scale"],
                    zone_cap_fraction=tuning["zone_cap"],
                )
                max_step = tuning["rate"] * dt * ease_scale
                if abs(delta) > max_step:
                    delta = max_step if delta > 0.0 else -max_step
                new_yaw = cur_yaw + delta

            cam_rot.Set(Gf.Vec3d(float(cur_rot[0]), float(new_yaw), 0.0))
            self._sync_controller_yaw(new_yaw)
        except Exception:
            if target is not None:
                self._apply_yaw_instant(target)
            self._stop_face_turn()

    def _sync_controller_yaw(self, yaw: float) -> None:
        """Keep the movement controller's internal yaw in sync so it doesn't snap back."""
        try:
            if self._movement_controller and hasattr(self._movement_controller, "set_view_angles"):
                cur_pitch = 0.0
                try:
                    _, cur_pitch = self._movement_controller.get_view_angles()
                except Exception:
                    pass
                self._movement_controller.set_view_angles(float(yaw), cur_pitch)
        except Exception:
            pass

