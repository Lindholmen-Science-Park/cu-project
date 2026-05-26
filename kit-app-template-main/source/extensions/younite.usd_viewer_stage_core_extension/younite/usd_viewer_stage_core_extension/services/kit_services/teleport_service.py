from typing import Optional

import carb
from pxr import UsdGeom, Gf

from ..core_services.world_conventions import (
    PLAYER_CHARACTER_PATH,
    WORLD_ROOT_PATH,
    find_spawn_point_prim,
)


_CCT_UNAVAILABLE = object()


class TeleportService:
    """Service for teleporting the player character to spawn points or coordinates."""

    def __init__(self, movement_controller_reset_callback=None):
        self._cct_interface = None
        self._player_character_path = PLAYER_CHARACTER_PATH
        self._movement_controller_reset_callback = movement_controller_reset_callback
        self._cct_teleport_method = None

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

    def _resolve_player_path(self):
        try:
            import omni.usd as _omni_usd
            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return None, None

            path = str(self._player_character_path or PLAYER_CHARACTER_PATH)
            prim = stage.GetPrimAtPath(path)
            if prim and prim.IsValid():
                self._player_character_path = path
                return path, prim

            return None, None
        except Exception as e:
            print(f"Error resolving player path: {e}")
            return None, None

    def find_spawn_point(self, spawn_point_name: str):
        try:
            import omni.usd as _omni_usd
            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return None, None

            return find_spawn_point_prim(stage, spawn_point_name)
        except Exception as e:
            print(f"Error finding spawn point: {e}")
            return None, None

    def _read_spawn_point_transform(self, spawn_point_prim):
        """Pose to apply to the player.

        * **Direct child of ``/World``** (bird-eye, foyer, FP spawns, etc.):
          read **authored local ops verbatim** — this preserves the exact
          ``rotateXYZ`` / ``rotateYXZ`` triple the spawn was authored with
          (matrix→Euler decomposition does not round-trip these reliably,
          which previously broke ``PlayerSpawnPoint_02``).
        * **Nested under another Xform** (e.g. NPC meet point parented under
          ``/World/Red``): read the **composed world** transform via
          ``UsdGeom.XformCache`` so the spawn follows the avatar's
          rotation/translation through USD compose, with no per-frame work.
        """
        try:
            parent_path = str(spawn_point_prim.GetParent().GetPath())
        except Exception:
            parent_path = ""

        if parent_path != WORLD_ROOT_PATH:
            return self._read_spawn_point_transform_world(spawn_point_prim)

        spawn_transform = UsdGeom.Xformable(spawn_point_prim)
        spawn_translate = Gf.Vec3d(0, 0, 0)
        spawn_rotate = Gf.Vec3d(0, 0, 0)
        spawn_rotate_type = "rotateXYZ"

        translate_op = spawn_transform.GetTranslateOp()
        if translate_op:
            spawn_translate = translate_op.Get()

        rotate_op = spawn_transform.GetRotateXYZOp()
        if rotate_op:
            try:
                spawn_rotate = rotate_op.Get()
                spawn_rotate_type = "rotateXYZ"
            except Exception:
                rotate_op = spawn_transform.GetRotateYXZOp()
                if rotate_op:
                    try:
                        spawn_rotate = rotate_op.Get()
                        spawn_rotate_type = "rotateYXZ"
                    except Exception:
                        pass
        else:
            rotate_op = spawn_transform.GetRotateYXZOp()
            if rotate_op:
                try:
                    spawn_rotate = rotate_op.Get()
                    spawn_rotate_type = "rotateYXZ"
                except Exception:
                    pass

        return spawn_translate, spawn_rotate, spawn_rotate_type

    def _read_spawn_point_transform_world(self, spawn_point_prim):
        """Composed world translate + **body yaw only** for nested spawn prims.

        Used only when the spawn is parented somewhere other than ``/World`` (e.g.
        an NPC meet point under ``/World/Red``). The player rig is upright and
        only needs Y-axis body rotation — pitch/roll come from the camera + input
        controller. We compute yaw directly from the spawn's **world forward
        vector** (transform of local ``+Z``), which is robust to the avatar's
        ``xformOp:orient`` quat (full XYZ-Euler decomposition can pick a triple
        that isn't pure-Y, leaving the body in the wrong orientation).
        """
        import math

        from pxr import Usd, UsdGeom

        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        m = cache.GetLocalToWorldTransform(spawn_point_prim)
        wt = m.ExtractTranslation()
        spawn_translate = Gf.Vec3d(float(wt[0]), float(wt[1]), float(wt[2]))

        fwd = m.TransformDir(Gf.Vec3d(0.0, 0.0, 1.0))
        fx, fz = float(fwd[0]), float(fwd[2])
        if (fx * fx + fz * fz) < 1e-12:
            yaw_deg = 0.0
        else:
            # Kit convention: yaw 0° looks down +Z, +X is 90° (atan2(x, z)).
            yaw_deg = math.degrees(math.atan2(fx, fz))
        spawn_rotate = Gf.Vec3d(0.0, yaw_deg, 0.0)
        return spawn_translate, spawn_rotate, "rotateXYZ"

    def _apply_transform_to_player(self, player_path, player_prim, spawn_translate, spawn_rotate, spawn_rotate_type):
        import omni.usd as _omni_usd
        stage = _omni_usd.get_context().get_stage()
        if not stage:
            return

        player_xform = UsdGeom.Xformable(player_prim)

        existing_translate_op = player_xform.GetTranslateOp()
        translate_op = existing_translate_op if existing_translate_op else player_xform.AddTranslateOp()
        translate_op.Set(spawn_translate)

        cct = self._get_cct_interface()
        if cct:
            try:
                if hasattr(cct, "teleport"):
                    cct.teleport(player_path, spawn_translate[0], spawn_translate[1], spawn_translate[2])
                elif hasattr(cct, "set_position"):
                    cct.set_position(player_path, spawn_translate[0], spawn_translate[1], spawn_translate[2])
            except Exception:
                pass

        if spawn_rotate_type == "rotateYXZ":
            rotate_op = player_xform.GetRotateYXZOp()
            if not rotate_op:
                rotate_op = player_xform.AddRotateYXZOp()
        else:
            rotate_op = player_xform.GetRotateXYZOp()
            if not rotate_op:
                rotate_op = player_xform.AddRotateXYZOp()

        rotate_op.Set(spawn_rotate)

        existing_scale_op = player_xform.GetScaleOp()
        scale_op = existing_scale_op if existing_scale_op else player_xform.AddScaleOp()
        scale_op.Set(Gf.Vec3d(1.0, 1.0, 1.0))

        player_xform.SetXformOpOrder([translate_op, rotate_op, scale_op])

        camera_path = f"{player_path}/first_person_camera"
        camera_prim = stage.GetPrimAtPath(camera_path)
        if camera_prim and camera_prim.IsValid():
            camera_xform = UsdGeom.Xformable(camera_prim)
            camera_rotate_op = camera_xform.GetRotateXYZOp()
            if not camera_rotate_op:
                camera_rotate_op = camera_xform.AddRotateXYZOp()
            camera_rotate_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))

        # Sync PlayerInputController to the camera we just wrote. The
        # controller stores ``_yaw`` / ``_pitch`` internally and writes
        # ``rot_op.Set(pitch, yaw, 0)`` on every frame that has mouse
        # / touch deltas, ignoring whatever we just authored on the
        # prim. Without this sync, the first user swipe after a spawn
        # teleport snaps the camera to ``stale_yaw + dx`` (the leftover
        # yaw from the previous FP session) instead of the expected
        # ``0 + dx``, producing the visible "jump to different
        # direction on first click" after a bird-eye → teleport-here
        # flow.
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            dispatch_to_events2(
                "younite.player.immediateViewAngles",
                {"yaw": 0.0, "pitch": 0.0},
            )
        except Exception:
            pass

        if self._movement_controller_reset_callback:
            try:
                self._movement_controller_reset_callback()
            except Exception:
                pass

    def teleport_to_spawn_point(self, spawn_point_name: str) -> bool:
        try:
            import omni.usd as _omni_usd
            stage = _omni_usd.get_context().get_stage()
            if not stage:
                print("No USD stage available for teleport")
                return False

            player_path, player_prim = self._resolve_player_path()
            if not player_prim:
                print("PlayerCharacter not found at any known path")
                return False

            spawn_point_prim, _spawn_point_path = self.find_spawn_point(spawn_point_name)
            if not spawn_point_prim:
                print(f"Spawn point {spawn_point_name} not found")
                return False

            spawn_translate, spawn_rotate, spawn_rotate_type = self._read_spawn_point_transform(spawn_point_prim)
            self._apply_transform_to_player(player_path, player_prim, spawn_translate, spawn_rotate, spawn_rotate_type)
            return True
        except Exception as e:
            print(f"Error teleporting player to spawn point: {e}")
            return False

    def teleport_to_pose(
        self,
        x: float,
        y: float,
        z: float,
        *,
        body_yaw_deg: float = 0.0,
    ) -> bool:
        """Teleport the player to an arbitrary world-space pose (position + body yaw).

        Uses the same `_apply_transform_to_player` machinery as
        `teleport_to_spawn_point`, so body rotation, camera reset to identity,
        scale, xform op order and the movement-controller reset all match the
        spawn-point flow exactly. Use this whenever a destination has no
        authored `PlayerSpawnPoint_*` (navmesh POIs such as restrooms / quiet
        zones, ad-hoc pin teleports, etc.); the caller computes the body yaw
        (typically facing the route destination) so the player lands oriented
        correctly without any post-teleport camera fix-ups.
        """
        try:
            import omni.usd as _omni_usd
            stage = _omni_usd.get_context().get_stage()
            if not stage:
                print("[TELEPORT] No USD stage available for pose teleport")
                return False

            player_path, player_prim = self._resolve_player_path()
            if not player_prim:
                print("[TELEPORT] PlayerCharacter not found; cannot pose-teleport")
                return False

            spawn_translate = Gf.Vec3d(float(x), float(y), float(z))
            spawn_rotate = Gf.Vec3d(0.0, float(body_yaw_deg), 0.0)
            self._apply_transform_to_player(
                player_path,
                player_prim,
                spawn_translate,
                spawn_rotate,
                "rotateXYZ",
            )
            return True
        except Exception as e:
            print(f"[TELEPORT] Pose teleport failure: {e}")
            return False

    def teleport_to_coordinates(
        self,
        x: float,
        y: float,
        z: float,
        *,
        camera_local_yaw_deg: Optional[float] = None,
        world_body_yaw_deg: Optional[float] = None,
    ) -> bool:
        """Teleport the player (and optionally orient them).

        Args:
            camera_local_yaw_deg: If provided, set the first-person
                camera's *local* yaw to this value. Useful when the
                player body should stay put and only the camera should
                rotate.
            world_body_yaw_deg: If provided, rotate the player body to
                face this world-space yaw (degrees, Kit convention:
                +Z is 0°, +X is 90°) *and* zero out the camera's local
                yaw so the view axis equals the body axis. This is the
                right mode for "face along a path after teleport"
                because the body rotation accumulates with the camera's
                local rotation — setting camera local alone (without
                touching body yaw) means the final world yaw is
                ``body_yaw + camera_local_yaw``, and every spawn point
                has a different body yaw. When both arguments are
                provided, ``world_body_yaw_deg`` wins (it assigns body
                and camera together for a deterministic view).
        """
        try:
            import omni.usd as _omni_usd

            player_path, player_prim = self._resolve_player_path()
            if not player_prim:
                print("[TELEPORT] PlayerCharacter not found; cannot teleport")
                return False

            translate = Gf.Vec3d(float(x), float(y), float(z))

            player_xform = UsdGeom.Xformable(player_prim)
            existing_translate_op = player_xform.GetTranslateOp()
            translate_op = existing_translate_op if existing_translate_op else player_xform.AddTranslateOp()
            translate_op.Set(translate)

            cct = self._get_cct_interface()
            if cct:
                try:
                    if hasattr(cct, "teleport"):
                        cct.teleport(player_path, x, y, z)
                    elif hasattr(cct, "set_position"):
                        cct.set_position(player_path, x, y, z)
                except Exception:
                    pass

            if self._movement_controller_reset_callback:
                try:
                    self._movement_controller_reset_callback()
                except Exception:
                    pass

            # Resolve effective yaw. ``world_body_yaw_deg`` takes
            # precedence because it guarantees a deterministic view
            # axis regardless of the previous spawn rotation.
            if world_body_yaw_deg is not None:
                try:
                    stage = _omni_usd.get_context().get_stage()
                    if stage:
                        # Player body yaw = target world yaw.
                        player_rot = (
                            player_xform.GetRotateXYZOp()
                            or player_xform.AddRotateXYZOp()
                        )
                        player_rot.Set(Gf.Vec3d(0.0, float(world_body_yaw_deg), 0.0))

                        # Zero the camera's local rotation so world yaw
                        # equals body yaw. Without this, the camera's
                        # leftover local yaw from the last FP session
                        # would stack on top and offset the view.
                        cam_path = f"{player_path}/first_person_camera"
                        cam_prim = stage.GetPrimAtPath(cam_path)
                        if cam_prim and cam_prim.IsValid():
                            cam_xf = UsdGeom.Xformable(cam_prim)
                            cam_rot = cam_xf.GetRotateXYZOp() or cam_xf.AddRotateXYZOp()
                            cam_rot.Set(Gf.Vec3d(0.0, 0.0, 0.0))
                    # Sync the input controller: its internal ``_yaw``
                    # drives the per-frame camera-local rotation, so we
                    # must reset it to 0 too or the next frame will
                    # stomp the zero we just wrote.
                    try:
                        from younite.messaging_core_extension.message_utils import dispatch_to_events2

                        dispatch_to_events2(
                            "younite.player.immediateViewAngles",
                            {"yaw": 0.0, "pitch": 0.0},
                        )
                    except Exception:
                        pass
                except Exception:
                    pass
            elif camera_local_yaw_deg is not None:
                try:
                    stage = _omni_usd.get_context().get_stage()
                    if stage:
                        cam_path = f"{player_path}/first_person_camera"
                        cam_prim = stage.GetPrimAtPath(cam_path)
                        if cam_prim and cam_prim.IsValid():
                            cam_xf = UsdGeom.Xformable(cam_prim)
                            cam_rot = cam_xf.GetRotateXYZOp() or cam_xf.AddRotateXYZOp()
                            yaw = float(camera_local_yaw_deg)
                            cam_rot.Set(Gf.Vec3d(0.0, yaw, 0.0))
                    try:
                        from younite.messaging_core_extension.message_utils import dispatch_to_events2

                        dispatch_to_events2(
                            "younite.player.immediateViewAngles",
                            {"yaw": float(camera_local_yaw_deg), "pitch": 0.0},
                        )
                    except Exception:
                        pass
                except Exception:
                    pass

            return True
        except Exception as e:
            print(f"[TELEPORT] Teleport failure: {e}")
            return False

