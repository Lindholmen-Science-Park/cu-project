import carb
from pxr import Usd, UsdGeom, Gf

from ..core_services.world_conventions import (
    PLAYER_CHARACTER_PATH,
    PLAYER_FIRST_PERSON_CAMERA_NAME,
    player_camera_path,
)
from ..core_services.usd_xform_helpers import read_authored_world_transform


_CCT_UNAVAILABLE = object()


class CameraService:
    """Camera view switching and reset."""

    FIXED_CAMERA_ACTIVE_SETTING = "/younite/camera/fixedCameraActive"

    def __init__(self, stage_manager, movement_controller_reset_callback=None, teleport_service=None):
        self._stage_manager = stage_manager
        self._cct_interface = None
        self._player_character_path = PLAYER_CHARACTER_PATH
        self._movement_controller_reset_callback = movement_controller_reset_callback
        self._teleport_service = teleport_service
        self._VIEW_TYPE_SETTING = "/younite/camera/viewType"
        try:
            from ..core_services.world_conventions import get_default_view_type
            self._current_view_type = get_default_view_type()
        except Exception:
            self._current_view_type = "firstPerson"
        self._fixed_camera_active = False
        self._saved_player_camera_path = None
        # Player pose saved by enter_xform_view, restored by exit_xform_view.
        # None when no overlay is active. Single slot (no nesting).
        self._xform_view_saved_pose = None

    def _get_cct_interface(self):
        if self._cct_interface is None:
            try:
                from omni.physxcct.scripts import utils as nv_utils
                self._cct_interface = nv_utils.get_physx_cct_interface()
            except Exception as e:
                print(f"Could not get CCT interface: {e}")
                self._cct_interface = _CCT_UNAVAILABLE
        if self._cct_interface is _CCT_UNAVAILABLE:
            return None
        return self._cct_interface

    def _set_player_gravity(self, enabled: bool) -> bool:
        try:
            cct = self._get_cct_interface()
            if not cct:
                print("CCT interface not available for gravity control")
                return False

            cct_path = str(self._player_character_path)
            try:
                if enabled:
                    cct.enable_gravity(cct_path)
                else:
                    cct.disable_gravity(cct_path)
                return True
            except Exception as e:
                print(f"Error setting player gravity: {e}")
                return False
        except Exception as e:
            print(f"Error accessing CCT interface: {e}")
            return False

    def move_player_to_spawnpoint(self, spawn_point_name: str, apply_gravity: "bool | None" = None) -> bool:
        ok = self._teleport_player_to_spawn_point(spawn_point_name)
        if not ok:
            return False
        if apply_gravity is not None:
            try:
                self._set_player_gravity(bool(apply_gravity))
            except Exception:
                pass
        return True

    def _apply_view_type(self, view_type: str) -> bool:
        """Set view-type state, dispatch events, and rebind the viewport camera.

        This is the single source of truth for all view-type transitions.
        It does NOT teleport — callers handle positioning separately.
        """
        try:
            from omni.kit.viewport.utility import get_active_viewport
            import omni.usd

            self._current_view_type = view_type
            try:
                carb.settings.get_settings().set(self._VIEW_TYPE_SETTING, str(view_type))
            except Exception:
                pass
            try:
                ed = carb.eventdispatcher.get_eventdispatcher()
                ed.dispatch_event("younite.camera.viewTypeChanged", {"viewType": str(view_type)})
            except Exception:
                pass

            resolved_player_path = str(self._player_character_path or PLAYER_CHARACTER_PATH)
            camera_path = player_camera_path(
                player_path=resolved_player_path,
                camera_name=PLAYER_FIRST_PERSON_CAMERA_NAME,
            )

            stage = omni.usd.get_context().get_stage()
            if stage:
                cam_prim = stage.GetPrimAtPath(camera_path)
                if cam_prim and cam_prim.IsValid():
                    viewport = get_active_viewport()
                    if viewport:
                        viewport.set_active_camera(camera_path)

            return True
        except Exception as e:
            print(f"[camera_service] _apply_view_type error: {e}")
            return False

    def set_view_type(self, view_type: str):
        """Update the current view type without teleporting or switching cameras."""
        self._apply_view_type(view_type)

    def _teleport_player_to_spawn_point(self, spawn_point_name: str) -> bool:
        if self._teleport_service:
            return self._teleport_service.teleport_to_spawn_point(spawn_point_name)
        print("TeleportService not available; cannot teleport to spawn point")
        return False

    def reset_camera(self):
        try:
            import omni.usd
            from omni.kit.viewport.utility import get_active_viewport_camera_string
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                raise RuntimeError("No stage available for camera reset")

            camera_prim = stage.GetPrimAtPath(get_active_viewport_camera_string())
            if not camera_prim:
                raise RuntimeError("Active camera prim not found")

            edit_context = Usd.EditContext(stage, Usd.EditTarget(stage.GetSessionLayer()))
            with edit_context:
                for name, value in self._stage_manager._camera_attrs.items():
                    attr = camera_prim.GetAttribute(name)
                    attr.Set(value)

            try:
                ed = carb.eventdispatcher.get_eventdispatcher()
                ed.dispatch_event("resetStageResponse", {"result": "success", "error": ""})
            except Exception:
                pass
        except Exception as e:
            try:
                ed = carb.eventdispatcher.get_eventdispatcher()
                ed.dispatch_event("resetStageResponse", {"result": "error", "error": str(e)})
            except Exception:
                pass

    def switch_camera_view(self, view_type: str, *, spawn_point: str = "") -> bool:
        """Switch between first-person and bird's-eye view.

        Teleports to the default spawnpoint for the view type unless
        ``spawn_point`` overrides it (e.g. "PlayerSpawnPoint_Arena").

        View type is applied before teleport so LOD and other view-type listeners
        see the correct mode before the player is moved.
        """
        try:
            if view_type == "firstPerson":
                target = spawn_point or "PlayerSpawnPoint_01"
            elif view_type == "birdEye":
                target = spawn_point or "PlayerSpawnPoint_02"
            else:
                print(f"Unknown view type: {view_type}")
                return False

            self._apply_view_type(view_type)
            self.move_player_to_spawnpoint(target, apply_gravity=None)
            return True
        except Exception as e:
            print(f"[camera] switch_camera_view failed: {e}")
            return False

    def is_fixed_camera_active(self) -> bool:
        return bool(getattr(self, "_fixed_camera_active", False))

    def switch_to_fixed_camera(self, camera_prim_path: str) -> bool:
        """Switch viewport to a scene camera (watch-only; no movement). Saves player camera for restore."""
        try:
            from omni.kit.viewport.utility import get_active_viewport
            import omni.usd

            path = str(camera_prim_path or "").strip()
            if not path:
                return False

            usd_context = omni.usd.get_context()
            stage = usd_context.get_stage()
            if not stage:
                print("No USD stage for fixed camera switch")
                return False

            prim = stage.GetPrimAtPath(path)
            if not (prim and prim.IsValid() and prim.IsA(UsdGeom.Camera)):
                print(f"Fixed camera not found or not a Camera: {path}")
                return False

            resolved_player_path = str(self._player_character_path or PLAYER_CHARACTER_PATH)
            player_cam = player_camera_path(player_path=resolved_player_path, camera_name=PLAYER_FIRST_PERSON_CAMERA_NAME)
            self._saved_player_camera_path = player_cam
            self._fixed_camera_active = True
            try:
                carb.settings.get_settings().set(self.FIXED_CAMERA_ACTIVE_SETTING, True)
            except Exception:
                pass

            viewport = get_active_viewport()
            if not viewport:
                print("No active viewport for fixed camera")
                return False
            viewport.set_active_camera(path)

            self._dispatch_fixed_camera_status(active=True, camera_prim_path=path)
            return True
        except Exception as e:
            self._fixed_camera_active = False
            self._saved_player_camera_path = None
            try:
                carb.settings.get_settings().set(self.FIXED_CAMERA_ACTIVE_SETTING, False)
            except Exception:
                pass
            self._dispatch_fixed_camera_status(active=False, error=str(e))
            print(f"Fixed camera switch failed: {e}")
            return False

    def exit_fixed_camera(self) -> bool:
        """Restore viewport to player camera and clear fixed-camera state."""
        try:
            from omni.kit.viewport.utility import get_active_viewport
            import omni.usd

            self._fixed_camera_active = False
            try:
                carb.settings.get_settings().set(self.FIXED_CAMERA_ACTIVE_SETTING, False)
            except Exception:
                pass

            restore_path = getattr(self, "_saved_player_camera_path", None) or player_camera_path(
                player_path=str(self._player_character_path or PLAYER_CHARACTER_PATH),
                camera_name=PLAYER_FIRST_PERSON_CAMERA_NAME,
            )
            self._saved_player_camera_path = None

            usd_context = omni.usd.get_context()
            stage = usd_context.get_stage()
            if stage and stage.GetPrimAtPath(restore_path) and stage.GetPrimAtPath(restore_path).IsValid():
                viewport = get_active_viewport()
                if viewport:
                    viewport.set_active_camera(restore_path)

            self._dispatch_fixed_camera_status(active=False)
            return True
        except Exception as e:
            self._dispatch_fixed_camera_status(active=False, error=str(e))
            print(f"Exit fixed camera failed: {e}")
            return False

    def enter_xform_view(self, xform_prim_path: str) -> bool:
        """Teleport the player to *xform_prim_path*'s authored pose for an overlay session.

        Used by spatial-sound + 360°-video overlays so the user views
        the experience from where it was recorded. Saves the previous
        pose so ``exit_xform_view`` can restore it verbatim.

        Reads the pose via ``read_authored_world_transform`` to skip
        the iconGroup spin-loop's session-layer overrides (otherwise
        the landing yaw varies with click timing).

        Always dispatches ``xformViewCameraReady`` so the web side
        can gate overlay mount on the WebRTC frame at the new pose
        (teleport is synchronous; frame delivery isn't).

        Don't switch to a temp camera here — every renderer/input
        path is wired to the player camera (sky, drag-look, FOV,
        fixedCameraStatus...), so swapping bind causes black-sky /
        broken-drag / flicker regressions. Teleport sidesteps all
        of that.
        """
        try:
            import omni.usd

            xform_prim_path = str(xform_prim_path or "").strip()
            if not xform_prim_path:
                self._dispatch_xform_view_ready(xform_prim_path, ok=False)
                return False

            stage = omni.usd.get_context().get_stage()
            if not stage:
                self._dispatch_xform_view_ready(xform_prim_path, ok=False)
                return False

            xform_prim = stage.GetPrimAtPath(xform_prim_path)
            if not (xform_prim and xform_prim.IsValid()):
                print(f"[camera_service] enter_xform_view: prim not found {xform_prim_path}")
                self._dispatch_xform_view_ready(xform_prim_path, ok=False)
                return False

            pose = read_authored_world_transform(stage, xform_prim)
            if pose is None:
                print(
                    f"[camera_service] enter_xform_view: cannot read authored pose for {xform_prim_path}"
                )
                self._dispatch_xform_view_ready(xform_prim_path, ok=False)
                return False
            (tx, ty, tz), yaw_deg = pose

            # Capture before teleporting. Don't overwrite — a second
            # enter while active must still restore to the *original*
            # pose, not the previous marker.
            if self._xform_view_saved_pose is None:
                self._xform_view_saved_pose = self._capture_player_pose()

            # Reuse teleport_service for CCT sync, body rotation,
            # immediateViewAngles, and movement-controller reset.
            ok = False
            if self._teleport_service:
                ok = self._teleport_service.teleport_to_coordinates(
                    float(tx),
                    float(ty),
                    float(tz),
                    world_body_yaw_deg=float(yaw_deg),
                )
            if not ok:
                # Keep saved pose so exit_xform_view stays a clean no-op.
                print(
                    f"[camera_service] enter_xform_view: teleport_to_coordinates failed for {xform_prim_path}"
                )
                self._dispatch_xform_view_ready(xform_prim_path, ok=False)
                return False

            self._dispatch_xform_view_ready(xform_prim_path, ok=True)
            return True
        except Exception as e:
            print(f"[camera_service] enter_xform_view failed: {e}")
            self._dispatch_xform_view_ready(xform_prim_path, ok=False)
            return False

    def exit_xform_view(self) -> bool:
        """Restore the pose saved by ``enter_xform_view``. Idempotent."""
        try:
            saved = self._xform_view_saved_pose
            self._xform_view_saved_pose = None
            if saved is None:
                return True
            return self._restore_player_pose(saved)
        except Exception as e:
            print(f"[camera_service] exit_xform_view failed: {e}")
            return False

    def _capture_player_pose(self) -> "dict | None":
        """Snapshot translate + body yaw + camera local yaw/pitch as plain floats."""
        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return None

            player_path = str(self._player_character_path or PLAYER_CHARACTER_PATH)
            player_prim = stage.GetPrimAtPath(player_path)
            if not (player_prim and player_prim.IsValid()):
                return None

            player_xf = UsdGeom.Xformable(player_prim)
            translate = Gf.Vec3d(0.0, 0.0, 0.0)
            t_op = player_xf.GetTranslateOp()
            if t_op:
                v = t_op.Get()
                if v is not None:
                    translate = Gf.Vec3d(float(v[0]), float(v[1]), float(v[2]))

            body_yaw = 0.0
            r_op = player_xf.GetRotateXYZOp() or player_xf.GetRotateYXZOp()
            if r_op:
                v = r_op.Get()
                if v is not None:
                    body_yaw = float(v[1])

            cam_yaw = 0.0
            cam_pitch = 0.0
            cam_path = f"{player_path}/{PLAYER_FIRST_PERSON_CAMERA_NAME}"
            cam_prim = stage.GetPrimAtPath(cam_path)
            if cam_prim and cam_prim.IsValid():
                cam_xf = UsdGeom.Xformable(cam_prim)
                cr_op = cam_xf.GetRotateXYZOp()
                if cr_op:
                    v = cr_op.Get()
                    if v is not None:
                        cam_pitch = float(v[0])
                        cam_yaw = float(v[1])

            return {
                "translate": (float(translate[0]), float(translate[1]), float(translate[2])),
                "body_yaw_deg": body_yaw,
                "cam_yaw_deg": cam_yaw,
                "cam_pitch_deg": cam_pitch,
            }
        except Exception as e:
            print(f"[camera_service] _capture_player_pose failed: {e}")
            return None

    def _restore_player_pose(self, saved: dict) -> bool:
        """Write saved pose to player + camera, sync CCT + PlayerInputController.

        Bypasses ``teleport_to_coordinates`` — that helper zeros the
        camera local rotation, but we need to restore the user's
        exact pitch/yaw so the round-trip is invisible.
        """
        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return False

            player_path = str(self._player_character_path or PLAYER_CHARACTER_PATH)
            player_prim = stage.GetPrimAtPath(player_path)
            if not (player_prim and player_prim.IsValid()):
                return False

            tx, ty, tz = saved["translate"]
            body_yaw = float(saved["body_yaw_deg"])
            cam_yaw = float(saved["cam_yaw_deg"])
            cam_pitch = float(saved["cam_pitch_deg"])

            player_xf = UsdGeom.Xformable(player_prim)
            t_op = player_xf.GetTranslateOp() or player_xf.AddTranslateOp()
            t_op.Set(Gf.Vec3d(tx, ty, tz))

            # CCT capsule is independent of the USD translate op —
            # sync it or the capsule snaps back next physics step.
            cct = self._get_cct_interface()
            if cct:
                try:
                    if hasattr(cct, "teleport"):
                        cct.teleport(player_path, tx, ty, tz)
                    elif hasattr(cct, "set_position"):
                        cct.set_position(player_path, tx, ty, tz)
                except Exception:
                    pass

            r_op = player_xf.GetRotateXYZOp() or player_xf.AddRotateXYZOp()
            r_op.Set(Gf.Vec3d(0.0, body_yaw, 0.0))

            cam_path = f"{player_path}/{PLAYER_FIRST_PERSON_CAMERA_NAME}"
            cam_prim = stage.GetPrimAtPath(cam_path)
            if cam_prim and cam_prim.IsValid():
                cam_xf = UsdGeom.Xformable(cam_prim)
                cr_op = cam_xf.GetRotateXYZOp() or cam_xf.AddRotateXYZOp()
                cr_op.Set(Gf.Vec3d(cam_pitch, cam_yaw, 0.0))

            # Sync PlayerInputController state — without this the
            # next swipe writes its stale yaw/pitch and undoes the
            # restore. Same pattern as teleport_service.
            try:
                from younite.messaging_core_extension.message_utils import (
                    dispatch_to_events2,
                )

                dispatch_to_events2(
                    "younite.player.immediateViewAngles",
                    {"yaw": cam_yaw, "pitch": cam_pitch},
                )
            except Exception:
                pass

            if self._movement_controller_reset_callback:
                try:
                    self._movement_controller_reset_callback()
                except Exception:
                    pass

            return True
        except Exception as e:
            print(f"[camera_service] _restore_player_pose failed: {e}")
            return False

    def _dispatch_xform_view_ready(self, prim_path: str, ok: bool) -> None:
        """Ack the web side. Always fires (even on failure) so the UI never wedges."""
        try:
            ed = carb.eventdispatcher.get_eventdispatcher()
            payload = {"primPath": str(prim_path or ""), "ok": bool(ok)}
            ed.dispatch_event("xformViewCameraReady", payload)
        except Exception:
            pass

    def _dispatch_fixed_camera_status(self, active: bool, camera_prim_path: str = "", error: str = "") -> None:
        try:
            ed = carb.eventdispatcher.get_eventdispatcher()
            payload = {"active": active}
            if camera_prim_path:
                payload["cameraPrimPath"] = camera_prim_path
                payload["cameraId"] = camera_prim_path.split("/")[-1] if "/" in camera_prim_path else camera_prim_path
            if error:
                payload["error"] = error
            ed.dispatch_event("fixedCameraStatus", payload)
        except Exception:
            pass

