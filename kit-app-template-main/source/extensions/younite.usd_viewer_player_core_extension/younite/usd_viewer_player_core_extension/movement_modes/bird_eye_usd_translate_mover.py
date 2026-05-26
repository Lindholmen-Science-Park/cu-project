from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


class BirdEyeUsdTranslateMover:
    """
    Bird-eye movement implementation.

    This is intentionally **not** PhysX/CCT-based: it moves the player prim directly
    by writing a USD translate op, while keeping Y locked to the initial height.
    """

    def __init__(self):
        self._locked_height: Optional[float] = None

    def reset(self) -> None:
        self._locked_height = None

    def drive(
        self,
        *,
        stage: Any,
        player_path: str,
        camera_path: Optional[str],
        movement_state: Dict[str, Any],
        dt: float,
        speed_multiplier: float,
        fallback_yaw_deg: float = 0.0,
    ) -> bool:
        """
        Returns True if handled (bird-eye path), False otherwise.
        """
        if not stage:
            return False

        try:
            from pxr import UsdGeom, Usd, Gf

            prim = stage.GetPrimAtPath(str(player_path))
            if not (prim and prim.IsValid()):
                return False

            xform = UsdGeom.Xformable(prim)
            m = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            pos = (
                m.ExtractTranslation()
                if hasattr(m, "ExtractTranslation")
                else Gf.Vec3d(m[3][0], m[3][1], m[3][2])
            )
            if self._locked_height is None:
                self._locked_height = float(pos[1])

            # Input: analog (mobile) or WASD (desktop)
            if "forward" in movement_state and "right" in movement_state:
                f = float(movement_state.get("forward", 0.0))
                r = float(movement_state.get("right", 0.0))
            else:
                f = (1.0 if movement_state.get("W", False) else 0.0) + (-1.0 if movement_state.get("S", False) else 0.0)
                r = (1.0 if movement_state.get("D", False) else 0.0) + (-1.0 if movement_state.get("A", False) else 0.0)

            # Derive pan basis from the camera's *world* orientation, not its
            # local RotateXYZ op. In bird-eye the camera's local rotation is
            # zeroed on teleport while the player body carries the spawn
            # rotation, so reading `rot[1]` would give 0 and pan directions
            # would lock to world +Z / -X regardless of which way the user is
            # actually looking. ComputeLocalToWorldTransform picks up rotation
            # at any level of the transform hierarchy, so this works
            # correctly after any spawn or runtime camera-angle change.
            #
            # USD camera convention: local -Z is forward, +X is right, +Y is up.
            # We project those world vectors onto the XZ ground plane so panning
            # always follows the screen-up / screen-right direction.
            forward_dir: Gf.Vec3d = Gf.Vec3d(0.0, 0.0, 1.0)
            right_dir: Gf.Vec3d = Gf.Vec3d(1.0, 0.0, 0.0)
            basis_from_matrix = False
            try:
                if camera_path:
                    cam_prim = stage.GetPrimAtPath(str(camera_path))
                    if cam_prim and cam_prim.IsValid():
                        cam_xf = UsdGeom.Xformable(cam_prim)
                        cam_m = cam_xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                        fwd_w = cam_m.TransformDir(Gf.Vec3d(0.0, 0.0, -1.0))
                        rgt_w = cam_m.TransformDir(Gf.Vec3d(1.0, 0.0, 0.0))
                        fwd_xz = Gf.Vec3d(float(fwd_w[0]), 0.0, float(fwd_w[2]))
                        rgt_xz = Gf.Vec3d(float(rgt_w[0]), 0.0, float(rgt_w[2]))
                        fl = fwd_xz.GetLength()
                        rl = rgt_xz.GetLength()
                        if fl > 1e-6 and rl > 1e-6:
                            forward_dir = fwd_xz / fl
                            right_dir = rgt_xz / rl
                            basis_from_matrix = True
            except Exception:
                pass

            if not basis_from_matrix:
                # Fallback: use the yaw the caller supplied (input controller).
                yaw_rad = math.radians(float(fallback_yaw_deg or 0.0))
                forward_dir = Gf.Vec3d(-math.sin(yaw_rad), 0.0, math.cos(yaw_rad))
                right_dir = Gf.Vec3d(-math.cos(yaw_rad), 0.0, -math.sin(yaw_rad))

            tr_op = xform.GetTranslateOp() or xform.AddTranslateOp()
            cur_local = tr_op.Get() if tr_op.Get() else Gf.Vec3d(0.0, 0.0, 0.0)

            if f != 0.0 or r != 0.0:
                mag = (f * f + r * r) ** 0.5
                if mag > 0.0:
                    f /= mag
                    r /= mag
                base_speed = 10000.0
                bird_eye_speed_multiplier = 8.0
                move_speed = float(base_speed) * float(speed_multiplier) * float(bird_eye_speed_multiplier)
                delta = (forward_dir * (f * move_speed * float(dt))) + (right_dir * (r * move_speed * float(dt)))
                new_pos = Gf.Vec3d(
                    float(cur_local[0] + delta[0]),
                    float(self._locked_height),
                    float(cur_local[2] + delta[2]),
                )
                tr_op.Set(new_pos)
            else:
                # Maintain locked height even if idle
                if cur_local and abs(float(cur_local[1]) - float(self._locked_height)) > 1e-4:
                    tr_op.Set(Gf.Vec3d(float(cur_local[0]), float(self._locked_height), float(cur_local[2])))

            return True
        except Exception:
            return False

