import omni.ext

from .inputs import PlayerInputController
from .inputs.mobile import WebInputWiring, WebJoystickInput
from .inputs.point_click import NavigationOrchestratorService, PointClickAutoMover, TouchLookHandler
from .movement_modes import (
    BirdEyeFramer,
    BirdEyeYawService,
    BirdEyeZoomService,
    ManualMovementRouter,
)
from .player_core import JumpController, PhysxBootstrap, MovementSpeedTuner
from .runtime.update_loop import PlayerUpdateLoop
from .services import PlayerLocationService
from .wiring.settings_watchers import SettingsWatchers
from .wiring.stage_events import StageEventWiring


class PlayerCoreExtension(omni.ext.IExt):
    """
    Player core extension (movement loop + lazy CCT).

    On startup, creates PlayerCharacter and binds camera (lightweight, no PhysX CCT).
    Point-and-click is the default mode (direct USD translate, navmesh waypoints).
    PhysX CCT is only activated on-demand when user selects WASD/joystick mode.
    """

    READY_FOR_PLAYER_SETTING = "/younite/player/readyForPlayer"
    PLAYER_READY_SETTING = "/younite/player/ready"
    MOVEMENT_SPEED_SETTING = "/younite/player/movementSpeedMultiplier"
    CAMERA_VIEW_TYPE_SETTING = "/younite/camera/viewType"

    def get_player_location_service(self):
        """Return the PlayerLocationService for use by other extensions (e.g. interactions range gating)."""
        return getattr(self, "_player_location_service", None)

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id

        try:
            import carb.settings as carb_settings
            self._settings = carb_settings.get_settings()
        except Exception:
            self._settings = None

        self._tasks = []

        # PhysX/CCT bootstrapping (now supports lightweight + on-demand CCT)
        self._physx_bootstrap = PhysxBootstrap(self)
        self._speed_tuner = MovementSpeedTuner(self)
        self._jump_controller = JumpController(self)

        # Movement / player state
        self._nvidia_controls_active = False
        self._nvidia_input_bound = False
        self._movement_speed_multiplier = 1.0
        self._camera_view_type = "firstPerson"

        self._manual_input_enabled = True

        self._player_character_path = None
        self._camera_path = None
        self._nv_cct_interface = None
        self._nv_character_controller = None
        self._physx_initialized = False
        self._player_initialized = False

        # Input controller (aggregates desktop + mobile joystick + touch look)
        try:
            self._web_joystick = WebJoystickInput()
            self._touch_look_handler = TouchLookHandler()
            self._movement_controller = PlayerInputController(
                movement_callback=self._on_movement_update,
                jump_callback=self.jump,
                get_camera_path=lambda: getattr(self, "_camera_path", None)
                or f"{getattr(self, '_player_character_path', '/World/PlayerCharacter')}/first_person_camera",
                get_view_type=lambda: getattr(self, "_camera_view_type", "firstPerson"),
                mobile_joystick=self._web_joystick,
                touch_look=self._touch_look_handler,
            )
        except Exception as e:
            self._movement_controller = None
            self._touch_look_handler = None
            print(f"[player_core] Could not create PlayerInputController: {e}")

        # Point&click auto-move (player only)
        self._point_click_mover = PointClickAutoMover(
            route_id="player",
            arrive_threshold=50.0,
            turn_rate_deg_per_s=124.0,
            get_stage=lambda: __import__("omni.usd").usd.get_context().get_stage(),
            get_player_path=lambda: getattr(self, "_player_character_path", None) or "/World/PlayerCharacter",
            get_camera_path=lambda: getattr(self, "_camera_path", None) or f"{getattr(self, '_player_character_path', '/World/PlayerCharacter')}/first_person_camera",
            get_speed_multiplier=lambda: float(getattr(self, "_movement_speed_multiplier", 1.0)),
            get_movement_controller=lambda: getattr(self, "_movement_controller", None),
            get_touch_look=lambda: getattr(self, "_touch_look_handler", None),
            on_complete=self._on_auto_move_complete,
        )
        try:
            self._point_click_mover.start()
        except Exception:
            pass

        self._manual_movement = ManualMovementRouter(self)

        self._bird_eye_framer = BirdEyeFramer(self)
        self._bird_eye_zoom = BirdEyeZoomService(self)
        self._bird_eye_yaw = BirdEyeYawService(self)
        self._bird_eye_frame_subs = []
        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app

            _ed = carb.eventdispatcher.get_eventdispatcher()
            for evt_name in (
                "birdEyeFrameTarget",
                "birdEyeFrameRestore",
                "birdEyeZoomLevel",
                "birdEyeYawDelta",
                "birdEyeYawEnd",
                "birdEyePanFocusWorld",
            ):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(evt_name), evt_name
                    )
                except Exception:
                    pass

            def _on_frame_target(_evt):
                try:
                    self._bird_eye_framer.frame()
                except Exception as e:
                    print(f"[player_core] birdEyeFrameTarget handler failed: {e}")

            def _on_frame_restore(_evt):
                try:
                    self._bird_eye_framer.restore()
                except Exception as e:
                    print(f"[player_core] birdEyeFrameRestore handler failed: {e}")

            def _on_zoom_level(evt):
                try:
                    from younite.messaging_core_extension.message_utils import normalize_event_payload
                    pl = normalize_event_payload(getattr(evt, "payload", None) or {})
                    level = pl.get("level", pl.get("zoomLevel", 1.0))
                    self._bird_eye_zoom.set_zoom_level(float(level))
                except Exception as e:
                    print(f"[player_core] birdEyeZoomLevel handler failed: {e}")

            def _on_yaw_delta(evt):
                try:
                    from younite.messaging_core_extension.message_utils import normalize_event_payload
                    pl = normalize_event_payload(getattr(evt, "payload", None) or {})
                    delta = pl.get("deltaDeg", pl.get("delta", pl.get("dyawDeg", 0.0)))
                    self._bird_eye_yaw.queue_delta(float(delta))
                except Exception as e:
                    print(f"[player_core] birdEyeYawDelta handler failed: {e}")

            def _on_bird_eye_pan_focus_world(evt):
                try:
                    from younite.messaging_core_extension.message_utils import normalize_event_payload

                    pl = normalize_event_payload(getattr(evt, "payload", None) or {})
                    w = None
                    for k in ("worldPos", "endPos", "endWorldPos", "targetWorldPos"):
                        v = pl.get(k)
                        if isinstance(v, (list, tuple)) and len(v) >= 3:
                            try:
                                w = (float(v[0]), float(v[1]), float(v[2]))
                                break
                            except (TypeError, ValueError):
                                continue
                    if w is None:
                        return
                    self._bird_eye_pan_focus_world(float(w[0]), float(w[1]), float(w[2]))
                except Exception as e:
                    print(f"[player_core] birdEyePanFocusWorld handler failed: {e}")

            self._bird_eye_frame_subs.append(
                _ed.observe_event(
                    observer_name="younite.usd_viewer_player_core_extension/birdEyeFrameTarget",
                    event_name="birdEyeFrameTarget",
                    on_event=_on_frame_target,
                    order=0,
                )
            )
            self._bird_eye_frame_subs.append(
                _ed.observe_event(
                    observer_name="younite.usd_viewer_player_core_extension/birdEyeFrameRestore",
                    event_name="birdEyeFrameRestore",
                    on_event=_on_frame_restore,
                    order=0,
                )
            )
            self._bird_eye_frame_subs.append(
                _ed.observe_event(
                    observer_name="younite.usd_viewer_player_core_extension/birdEyeZoomLevel",
                    event_name="birdEyeZoomLevel",
                    on_event=_on_zoom_level,
                    order=0,
                )
            )
            def _on_yaw_end(_evt):
                try:
                    self._bird_eye_yaw.arm_coast()
                except Exception as e:
                    print(f"[player_core] birdEyeYawEnd handler failed: {e}")

            self._bird_eye_frame_subs.append(
                _ed.observe_event(
                    observer_name="younite.usd_viewer_player_core_extension/birdEyeYawDelta",
                    event_name="birdEyeYawDelta",
                    on_event=_on_yaw_delta,
                    order=0,
                )
            )
            self._bird_eye_frame_subs.append(
                _ed.observe_event(
                    observer_name="younite.usd_viewer_player_core_extension/birdEyeYawEnd",
                    event_name="birdEyeYawEnd",
                    on_event=_on_yaw_end,
                    order=0,
                )
            )
            self._bird_eye_frame_subs.append(
                _ed.observe_event(
                    observer_name="younite.usd_viewer_player_core_extension/birdEyePanFocusWorld",
                    event_name="birdEyePanFocusWorld",
                    on_event=_on_bird_eye_pan_focus_world,
                    order=0,
                )
            )
        except Exception as e:
            print(f"[player_core] bird-eye framer event subscribe failed: {e}")

        # Navigation/mode orchestrator with mode-change callback for lazy CCT
        self._nav_orchestrator = None
        try:
            self._nav_orchestrator = NavigationOrchestratorService(
                movement_controller=getattr(self, "_movement_controller", None),
                auto_mover=getattr(self, "_point_click_mover", None),
                mode_change_callback=self._on_movement_mode_changed,
                get_player_path=lambda: getattr(self, "_player_character_path", None) or "/World/PlayerCharacter",
                get_camera_path=lambda: getattr(self, "_camera_path", None)
                or f"{getattr(self, '_player_character_path', '/World/PlayerCharacter')}/first_person_camera",
            )
            self._nav_orchestrator.start()
            try:
                pcm = getattr(self, "_point_click_mover", None)
                no = getattr(self, "_nav_orchestrator", None)
                if pcm and no and hasattr(pcm, "set_is_face_turn_active"):
                    pcm.set_is_face_turn_active(no.is_face_turn_active)
            except Exception:
                pass
        except Exception as e:
            self._nav_orchestrator = None
            print(f"[player_core] nav orchestrator init failed: {e}")

        self._immediate_view_sub = None
        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            def _on_immediate_view_angles(evt):
                pl = normalize_event_payload(getattr(evt, "payload", None) or {})
                try:
                    yaw = float(pl.get("yaw", 0.0))
                    pitch = float(pl.get("pitch", 0.0))
                except (TypeError, ValueError):
                    return
                no = getattr(self, "_nav_orchestrator", None)
                if no and hasattr(no, "stop_face_turn_if_active"):
                    try:
                        no.stop_face_turn_if_active()
                    except Exception:
                        pass
                mc = getattr(self, "_movement_controller", None)
                if mc and hasattr(mc, "set_view_angles"):
                    try:
                        mc.set_view_angles(yaw, pitch)
                    except Exception:
                        pass

            _ed = carb.eventdispatcher.get_eventdispatcher()
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("younite.player.immediateViewAngles"),
                    "younite.player.immediateViewAngles",
                )
            except Exception:
                pass
            self._immediate_view_sub = _ed.observe_event(
                observer_name="younite.usd_viewer_player_core_extension/immediateViewAngles",
                event_name="younite.player.immediateViewAngles",
                on_event=_on_immediate_view_angles,
                order=0,
            )
        except Exception as e:
            print(f"[player_core] immediateViewAngles subscribe failed: {e}")

        # Player world-space location tracker
        try:
            self._player_location_service = PlayerLocationService(
                get_player_path=lambda: getattr(self, "_player_character_path", None) or "/World/PlayerCharacter",
                min_distance=1.0,
                min_print_interval_s=0.10,
                print_on_change=True,
            )
        except Exception as e:
            self._player_location_service = None
            print(f"[player_core] location service init failed: {e}")

        # Wiring modules
        self._settings_watchers = SettingsWatchers(self)
        self._settings_watchers.start()

        self._web_input = WebInputWiring(joystick=getattr(self, "_web_joystick", WebJoystickInput()))
        self._web_input.start()

        if getattr(self, "_touch_look_handler", None):
            self._touch_look_handler.start()

        self._stage_events = StageEventWiring(self)
        self._stage_events.start()

        self._update_loop = PlayerUpdateLoop(self)
        self._update_loop.start()

        # Expose instance for dependent extensions
        import sys
        _mod = sys.modules.get(__name__)
        if _mod is not None:
            _mod._instance = self

        print("[player_core] started")

    def _track_task(self, task):
        try:
            if hasattr(self, "_tasks") and self._tasks is not None:
                self._tasks.append(task)
        except Exception:
            pass
        return task

    def _maybe_init_player(self):
        """
        Run lightweight player setup once StageCore says the stage/timeline are ready.
        Creates PlayerCharacter and binds camera but does NOT activate CCT.
        Point-and-click is the default mode.
        """
        try:
            if getattr(self, "_player_initialized", False):
                return
            print("[player_core] readyForPlayer received -> setting up player character (lightweight)...")
            self._physx_bootstrap.setup_player_character()
            if getattr(self, "_player_initialized", False):
                try:
                    if self._settings:
                        self._settings.set(self.PLAYER_READY_SETTING, True)
                except Exception:
                    pass
                try:
                    import carb.eventdispatcher as _ed
                    _ed.get_eventdispatcher().dispatch_event("younite.player.ready", {"success": True})
                except Exception:
                    pass
                try:
                    from younite.usd_viewer_stage_core_extension.services.core_services.world_conventions import get_default_view_type
                    default_vt = get_default_view_type()
                except Exception:
                    default_vt = "firstPerson"
                try:
                    if self._settings:
                        self._settings.set(self.CAMERA_VIEW_TYPE_SETTING, default_vt)
                except Exception:
                    pass
                self._camera_view_type = default_vt
                try:
                    from younite.messaging_core_extension.message_utils import dispatch_to_events2
                    dispatch_to_events2("navigationStateSet", {
                        "movementMode": "pointClick",
                        "navigationEnabled": True,
                        "drawPath": False,
                        "autoMove": True,
                        "routeId": "player",
                    })
                except Exception:
                    pass
                print(f"[player_core] ✓ playerReady (default={default_vt}, no CCT)")
        except Exception as e:
            print(f"[player_core] player init failed: {e}")

    def _on_movement_mode_changed(self, new_mode: str):
        """
        Callback from NavigationOrchestratorService when movement mode changes.
        Activates/deactivates PhysX CCT on demand.

        Camera look (touch/mouse) stays active in all modes.  WASD/joystick
        movement is gated in _on_movement_update based on current mode.
        """
        try:
            if new_mode in ("wasd", "mobileJoystick"):
                if not getattr(self, "_physx_initialized", False):
                    print(f"[player_core] Mode changed to '{new_mode}' -> activating PhysX CCT...")
                    self._physx_bootstrap.activate_cct()
            elif new_mode == "pointClick":
                if getattr(self, "_physx_initialized", False):
                    print(f"[player_core] Mode changed to '{new_mode}' -> deactivating PhysX CCT...")
                    self._physx_bootstrap.deactivate_cct()
        except Exception as e:
            print(f"[player_core] mode change CCT toggle failed: {e}")

    def _on_auto_move_complete(self, route_id: str, reason: str):
        """Notify web UI when auto-move stops (arrival or cancellation). Clear path spheres when arrived so point-click trail is removed and does not linger when user then requests e.g. path to seats."""
        # Same world XYZ as ``get_seat_position`` / teleport — read before navmeshRouteStop clears seat target.
        seat_snap_world = None
        if reason == "arrived" and route_id == "seat_nav":
            try:
                from younite.navmesh_route_extension.seat_nav_target_bridge import (
                    get_seat_nav_snap_world_position,
                    get_seat_nav_target_seat_id,
                )
                from younite.navmesh_route_extension.services.kit_services.seat_lookup import (
                    get_seat_position,
                )

                seat_snap_world = get_seat_nav_snap_world_position()
                if not seat_snap_world:
                    sid = get_seat_nav_target_seat_id()
                    if sid:
                        seat_snap_world = get_seat_position(sid)
            except Exception:
                seat_snap_world = None

        # seat_nav: snap to exact seats_lookup (same as teleport) before notifying web so
        # celebration / playerFaceStadiumCenter runs at the final seat pose.
        if reason == "arrived" and route_id == "seat_nav":
            if seat_snap_world and len(seat_snap_world) >= 3:
                self._snap_player_to_seat_lookup_exact(seat_snap_world)
            else:
                print("[player_core] seat_nav arrived but no seats_lookup position; exact snap skipped")

        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2
            dispatch_to_events2("autoMoveStatus", {
                "routeId": route_id,
                "active": False,
                "reason": reason,
            })
            if reason == "arrived" and route_id:
                dispatch_to_events2("navmeshRouteStop", {"routeId": route_id})
        except Exception as e:
            print(f"[player_core] autoMoveStatus dispatch failed: {e}")

        if reason == "arrived" and route_id != "seat_nav":
            self._snap_player_to_ground_after_arrival()

    def _snap_player_to_seat_lookup_exact(self, pos) -> None:
        """Identical placement to seat teleport: TeleportService.teleport_to_coordinates."""
        try:
            ex, ey, ez = float(pos[0]), float(pos[1]), float(pos[2])
            from younite.usd_viewer_stage_core_extension.teleport_registry import get_teleport_service

            tp = get_teleport_service()
            if tp and tp.teleport_to_coordinates(ex, ey, ez):
                return
        except Exception as e:
            print(f"[player_core] seat snap TeleportService failed: {e}")
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom, Gf

            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return
            player_path = getattr(self, "_player_character_path", None) or "/World/PlayerCharacter"
            player_prim = stage.GetPrimAtPath(player_path)
            if not player_prim or not player_prim.IsValid():
                return
            xform = UsdGeom.Xformable(player_prim)
            tr_op = xform.GetTranslateOp()
            if not tr_op:
                tr_op = xform.AddTranslateOp()
            tr_op.Set(Gf.Vec3d(ex, ey, ez))
        except Exception as e:
            print(f"[player_core] seat lookup translate fallback failed: {e}")

    def _bird_eye_pan_focus_world(self, wx: float, wy: float, wz: float) -> bool:
        """Slide the bird-eye rig in XZ (same translate op as touch/WASD pan) so ``(wx,wy,wz)``
        lies on the active viewport camera's center ray at height ``wy``. Camera rotation is
        not modified."""
        try:
            if str(getattr(self, "_camera_view_type", "") or "") != "birdEye":
                return False
            import omni.usd as _omni_usd
            from pxr import UsdGeom, Gf, Usd

            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return False
            player_path = getattr(self, "_player_character_path", None) or "/World/PlayerCharacter"
            cam_path = getattr(self, "_camera_path", None) or f"{player_path}/first_person_camera"
            player_prim = stage.GetPrimAtPath(str(player_path))
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if not (player_prim and player_prim.IsValid() and cam_prim and cam_prim.IsValid()):
                return False

            cam_xf = UsdGeom.Xformable(cam_prim)
            cam_m = cam_xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            C = cam_m.ExtractTranslation()
            fwd = cam_m.TransformDir(Gf.Vec3d(0.0, 0.0, -1.0))
            fl = float(fwd.GetLength())
            if fl < 1e-8:
                return False
            fn = fwd / fl
            if abs(float(fn[1])) < 1e-5:
                return False
            t0 = (float(wy) - float(C[1])) / float(fn[1])
            if t0 <= 1e-4:
                return False
            gx = float(C[0]) + float(fn[0]) * t0
            gz = float(C[2]) + float(fn[2]) * t0
            dx = float(wx) - gx
            dz = float(wz) - gz
            if abs(dx) < 0.5 and abs(dz) < 0.5:
                try:
                    self._manual_movement.reset()
                except Exception:
                    pass
                return True

            p_xf = UsdGeom.Xformable(player_prim)
            tr_op = p_xf.GetTranslateOp()
            if not tr_op:
                tr_op = p_xf.AddTranslateOp()
            cur = tr_op.Get()
            if not cur:
                cur = Gf.Vec3d(0.0, 0.0, 0.0)
            tr_op.Set(
                Gf.Vec3d(float(cur[0]) + dx, float(cur[1]), float(cur[2]) + dz)
            )
            try:
                self._manual_movement.reset()
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"[player_core] _bird_eye_pan_focus_world failed: {e}")
            return False

    def _snap_player_to_ground_after_arrival(self):
        """After point-and-click arrival, correct small Y drift without falling through floors."""
        try:
            import asyncio
            asyncio.ensure_future(self._gentle_ground_snap())
        except Exception as e:
            print(f"[player_core] snap after arrival failed: {e}")

    async def _gentle_ground_snap(self):
        """NavMesh-based ground snap — corrects any accumulated Y drift after arrival."""
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom, Gf
            import omni.kit.app as _app

            await _app.get_app().next_update_async()

            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return
            player_path = getattr(self, "_player_character_path", None) or "/World/PlayerCharacter"
            player_prim = stage.GetPrimAtPath(player_path)
            if not player_prim or not player_prim.IsValid():
                return
            xform = UsdGeom.Xformable(player_prim)
            tr_op = xform.GetTranslateOp()
            if not tr_op:
                return
            cur = tr_op.Get()
            if not cur:
                return

            from younite.usd_viewer_player_core_extension.player_core.physx_bootstrap import PhysxBootstrap
            ground_y = PhysxBootstrap._navmesh_ground_y(float(cur[0]), float(cur[1]), float(cur[2]))
            if ground_y is None:
                return

            delta = float(cur[1]) - float(ground_y)
            if abs(delta) < 2.0:
                return

            tr_op.Set(Gf.Vec3d(float(cur[0]), float(ground_y), float(cur[2])))
        except Exception as e:
            print(f"[player_core] gentle_ground_snap failed: {e}")

    def _on_movement_update(self, dt: float, movement_state: dict):
        """Handle WASD/joystick movement updates via ManualMovementRouter.

        In pointClick mode, WASD/joystick input is ignored (no CCT needed).
        Bird-eye touch drag still works because it uses direct USD translate.
        CCT is only active in wasd/mobileJoystick modes (activated via
        _on_movement_mode_changed when user explicitly switches mode).
        """
        try:
            manual_active = False
            if isinstance(movement_state, dict):
                if "forward" in movement_state and "right" in movement_state:
                    try:
                        manual_active = (abs(float(movement_state.get("forward", 0.0))) > 1e-3) or (
                            abs(float(movement_state.get("right", 0.0))) > 1e-3
                        )
                    except Exception:
                        manual_active = False
                else:
                    manual_active = bool(
                        movement_state.get("W", False)
                        or movement_state.get("A", False)
                        or movement_state.get("S", False)
                        or movement_state.get("D", False)
                    )
            self._manual_move_active = bool(manual_active)
        except Exception:
            self._manual_move_active = False

        bird_eye_touch = bool(movement_state.get("_bird_eye_touch_drag", False))

        # In pointClick mode, only allow bird-eye touch drag (direct USD translate).
        # WASD/joystick input is suppressed — user must explicitly switch mode first.
        nav = getattr(self, "_nav_orchestrator", None)
        current_mode = "pointClick"
        try:
            if nav and hasattr(nav, "_state"):
                current_mode = nav._state.movement_mode
        except Exception:
            pass

        if current_mode == "pointClick" and not bird_eye_touch:
            self._manual_move_active = False
            return

        self._drive_manual_movement(dt, movement_state)

    def set_movement_speed(self, speed_multiplier: float):
        return bool(self._speed_tuner.set_movement_speed(speed_multiplier))

    def jump(self):
        try:
            return bool(self._jump_controller.jump())
        except Exception:
            return False

    def _drive_manual_movement(self, dt: float, movement_state: dict):
        """Forward manual input to the ManualMovementRouter."""
        try:
            if getattr(self, "_manual_movement", None):
                self._manual_movement.drive(dt, movement_state)
        except Exception:
            pass

    def _set_manual_input_enabled(self, enabled: bool) -> None:
        """Toggle manual input only on state change (avoid per-frame spam/reset)."""
        try:
            enabled = bool(enabled)
            if enabled == bool(getattr(self, "_manual_input_enabled", True)):
                return
            self._manual_input_enabled = enabled
            mc = getattr(self, "_movement_controller", None)
            if mc and hasattr(mc, "set_input_enabled"):
                mc.set_input_enabled(enabled)
        except Exception:
            pass

    def on_shutdown(self):
        try:
            for t in getattr(self, "_tasks", []) or []:
                try:
                    if hasattr(t, "cancel"):
                        t.cancel()
                except Exception:
                    pass
            self._tasks = []
        except Exception:
            pass

        try:
            if getattr(self, "_update_loop", None):
                self._update_loop.stop()
        except Exception:
            pass
        self._update_loop = None

        try:
            if getattr(self, "_stage_events", None):
                self._stage_events.stop()
        except Exception:
            pass
        self._stage_events = None

        try:
            if getattr(self, "_settings_watchers", None):
                self._settings_watchers.stop()
        except Exception:
            pass
        self._settings_watchers = None

        try:
            if getattr(self, "_web_input", None):
                self._web_input.stop()
        except Exception:
            pass
        self._web_input = None

        try:
            if getattr(self, "_touch_look_handler", None):
                self._touch_look_handler.stop()
        except Exception:
            pass
        self._touch_look_handler = None

        try:
            if getattr(self, "_point_click_mover", None):
                self._point_click_mover.shutdown()
        except Exception:
            pass

        try:
            if getattr(self, "_movement_controller", None):
                self._movement_controller.on_shutdown()
        except Exception:
            pass
        self._movement_controller = None

        try:
            if getattr(self, "_nav_orchestrator", None):
                self._nav_orchestrator.stop()
        except Exception:
            pass
        self._nav_orchestrator = None

        self._immediate_view_sub = None

        try:
            self._bird_eye_frame_subs = []
        except Exception:
            pass
        try:
            if getattr(self, "_bird_eye_zoom", None):
                self._bird_eye_zoom.snap_restore()
        except Exception:
            pass
        self._bird_eye_zoom = None
        self._bird_eye_framer = None

        try:
            if getattr(self, "_player_location_service", None):
                self._player_location_service.stop()
        except Exception:
            pass
        self._player_location_service = None

        import sys
        _mod = sys.modules.get(__name__)
        if _mod is not None and getattr(_mod, "_instance", None) is self:
            setattr(_mod, "_instance", None)

        self._point_click_mover = None
