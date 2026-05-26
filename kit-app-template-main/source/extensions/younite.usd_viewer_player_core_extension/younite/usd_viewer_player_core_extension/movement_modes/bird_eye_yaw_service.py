from __future__ import annotations

from typing import Any, Optional, Tuple

from younite.usd_viewer_player_core_extension.inputs.point_click.ease_helpers import (
    apply_exponential_coast,
)


class BirdEyeYawService:
    """Web-driven map rotation for the bird-eye view ("camera_self" pivot).

    Rotates the **player body** around **world +Y** by composing an
    additional yaw onto its existing ``xformOp:rotateXYZ`` Euler. The
    bird-eye camera is parented under the body, so:

    * the bird-eye view rotates around the body's pivot (= camera position
      in world XZ) — the player marker stays put, everything else swings
      around it;
    * `BirdEyeUsdTranslateMover.drive()` derives its pan basis from
      ``cam_xf.ComputeLocalToWorldTransform()``, so drag-pan automatically
      follows the new camera heading without any extra wiring.

    Why not write the camera's local ``RotateXYZ.z`` (the obvious "rotate
    around the look axis" guess)? In bird-eye the player body has a
    spawn rotation around ``(159°, -45°, 180°)`` that tilts the camera's
    local Z axis significantly off world +Y. Rotating around camera local
    Z on that tilted axis reads as a **roll** (horizon tilts diagonally),
    not a map rotation. Rotating the body around true world +Y avoids that
    entirely.

    Why not insert a new ``xformOp:rotateY:birdEyeYaw`` op into the body's
    ``xformOpOrder``? It would work, but mutating the op list on a
    runtime-managed prim adds a Hydra-invalidation surface area we don't
    need. Composing into the existing Euler is a value-only edit.

    Pitfall: the baseline Euler is captured on the **first** ``apply_delta``
    call after entering bird-eye. Re-decomposing the composed rotation
    every call would slowly drift through Gf's decomposition rounding.
    By recomposing each call as ``Ry(total_yaw) * baseline`` we always
    recover an exact Euler for any yaw, with no accumulated error.
    """

    # Decomposition is ambiguous within this band of body pitch (~±90° on
    # the Y component). The bird-eye spawn pitch is around -45°, so this
    # is purely defensive; if a future spawn lands inside the band the
    # service degrades gracefully (drops the apply, keeps the baseline).
    _GIMBAL_GUARD_DEG: float = 2.0

    # Post-release map rotation coast — very short (higher decay = shorter)
    COAST_DECAY_PER_SEC: float = 95.0
    COAST_STOP_VEL_DEG_S: float = 1.2

    def __init__(self, host: Any):
        self._h = host
        self._yaw_deg: float = 0.0
        # Body Euler at the moment the user first started rotating in
        # this bird-eye session. Cleared on snap_restore.
        self._baseline_euler: Optional[Tuple[float, float, float]] = None
        self._queued_delta_deg: float = 0.0
        self._coast_vel_deg_s: float = 0.0
        self._coast_armed: bool = False

    # -- Helpers ------------------------------------------------------------

    def _player_path(self) -> Optional[str]:
        h = self._h
        try:
            return getattr(h, "_player_character_path", None) or "/World/PlayerCharacter"
        except Exception:
            return None

    def _is_bird_eye(self) -> bool:
        try:
            return str(getattr(self._h, "_camera_view_type", "firstPerson") or "firstPerson") == "birdEye"
        except Exception:
            return False

    # -- Public API ---------------------------------------------------------

    def get_yaw_deg(self) -> float:
        return float(self._yaw_deg)

    def queue_delta(self, delta_deg: float) -> None:
        """Queue a web twist / rotate-drag delta for ``tick()`` (same frame)."""
        try:
            d = float(delta_deg)
        except (TypeError, ValueError):
            return
        if abs(d) <= 1e-6:
            return
        self._queued_delta_deg += d
        self._coast_armed = False
        self._coast_vel_deg_s = 0.0

    def arm_coast(self) -> None:
        """Called on ``birdEyeYawEnd`` after pointer-up on map rotation drag."""
        self._coast_armed = True

    def is_coasting(self) -> bool:
        return self._coast_armed and abs(self._coast_vel_deg_s) > self.COAST_STOP_VEL_DEG_S

    def tick(self, dt: float) -> bool:
        """
        Apply queued drag deltas and optional post-release coast.
        Returns True if USD was updated this frame.
        """
        if not self._is_bird_eye():
            return False
        dt = max(float(dt or 0.0), 1.0 / 240.0)

        if abs(self._queued_delta_deg) > 1e-6:
            d = float(self._queued_delta_deg)
            self._queued_delta_deg = 0.0
            self._coast_vel_deg_s = d / dt
            self._coast_armed = False
            return self.apply_delta(d)

        if not self._coast_armed:
            return False

        step, self._coast_vel_deg_s, active = apply_exponential_coast(
            self._coast_vel_deg_s,
            dt,
            decay_per_sec=self.COAST_DECAY_PER_SEC,
            stop_vel=self.COAST_STOP_VEL_DEG_S,
        )
        if not active:
            self._coast_armed = False
            return False
        if abs(step) <= 1e-6:
            return False
        return self.apply_delta(step)

    def apply_delta(self, delta_deg: float) -> bool:
        """Add ``delta_deg`` to the running yaw offset and write it to USD."""
        if not self._is_bird_eye():
            return False
        try:
            d = float(delta_deg)
        except (TypeError, ValueError):
            return False
        if d == 0.0:
            return True
        new_yaw = self._yaw_deg + d
        # Wrap to (-180, 180] so the stored value stays bounded.
        while new_yaw > 180.0:
            new_yaw -= 360.0
        while new_yaw <= -180.0:
            new_yaw += 360.0
        return self._write_yaw(new_yaw)

    def snap_restore(self) -> None:
        """Restore the body to its baseline rotation and forget state.

        Called from ``SettingsWatchers`` on every view-type change. If the
        user never rotated in this bird-eye session, this is a no-op
        (baseline was never captured).
        """
        try:
            if self._baseline_euler is not None:
                self._write_euler(self._baseline_euler)
        except Exception:
            pass
        self._yaw_deg = 0.0
        self._baseline_euler = None
        self._queued_delta_deg = 0.0
        self._coast_vel_deg_s = 0.0
        self._coast_armed = False

    # -- USD plumbing -------------------------------------------------------

    def _get_rot_op(self):
        """Return ``(Xformable, RotateXYZOp)`` for the player body, or ``None``."""
        try:
            import omni.usd
            from pxr import UsdGeom
        except Exception:
            return None
        try:
            path = self._player_path()
            if not path:
                return None
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return None
            prim = stage.GetPrimAtPath(str(path))
            if not (prim and prim.IsValid()):
                return None
            xf = UsdGeom.Xformable(prim)
            rot_op = xf.GetRotateXYZOp()
            if not rot_op:
                # Body should always have a rotateXYZ from teleport, but
                # add one if missing so the gesture still works on edge
                # cases (and we don't silently no-op).
                rot_op = xf.AddRotateXYZOp()
                rot_op.Set(__import__("pxr").Gf.Vec3d(0.0, 0.0, 0.0))
            return xf, rot_op
        except Exception:
            return None

    def _write_yaw(self, yaw_deg: float) -> bool:
        try:
            from pxr import Gf
        except Exception:
            return False

        got = self._get_rot_op()
        if got is None:
            return False
        _xf, rot_op = got

        # Capture baseline Euler the first time we touch the body in
        # this bird-eye session (lazy: nothing happens if the user never
        # rotates).
        if self._baseline_euler is None:
            cur = rot_op.Get()
            if cur is None:
                self._baseline_euler = (0.0, 0.0, 0.0)
            else:
                self._baseline_euler = (float(cur[0]), float(cur[1]), float(cur[2]))

        bx, by, bz = self._baseline_euler

        # Defensive gimbal guard. The bird-eye spawn pitch is ~-45° so
        # this never trips in practice; bail loudly rather than emit a
        # decomposition that snaps the camera around.
        if abs(abs(by) - 90.0) < float(self._GIMBAL_GUARD_DEG):
            print(
                f"[bird_eye_yaw] body pitch {by:.2f}° too close to ±90° "
                "for safe Euler decomposition — yaw delta dropped"
            )
            return False

        # USD RotateXYZ: matrix = Rz(z) * Ry(y) * Rx(x). Build the
        # baseline rotation by composing the same way, then prepend a
        # world-Y rotation to apply yaw at the parent (= world) level.
        baseline_rot = (
            Gf.Rotation(Gf.Vec3d(0, 0, 1), bz)
            * Gf.Rotation(Gf.Vec3d(0, 1, 0), by)
            * Gf.Rotation(Gf.Vec3d(1, 0, 0), bx)
        )
        yaw_world = Gf.Rotation(Gf.Vec3d(0, 1, 0), float(yaw_deg))
        target = yaw_world * baseline_rot

        # Decompose(axis0, axis1, axis2) returns (a0, a1, a2) such that
        # the rotation == Rotate(axis2, a2) * Rotate(axis1, a1) * Rotate(axis0, a0)
        # — which is exactly USD's RotateXYZ convention.
        try:
            angles = target.Decompose(
                Gf.Vec3d(1, 0, 0), Gf.Vec3d(0, 1, 0), Gf.Vec3d(0, 0, 1)
            )
        except Exception:
            return False

        new_euler = (float(angles[0]), float(angles[1]), float(angles[2]))
        ok = self._write_euler(new_euler)
        if ok:
            self._yaw_deg = float(yaw_deg)
        return ok

    def _write_euler(self, euler: Tuple[float, float, float]) -> bool:
        try:
            from pxr import Gf
        except Exception:
            return False
        got = self._get_rot_op()
        if got is None:
            return False
        _xf, rot_op = got
        try:
            rot_op.Set(Gf.Vec3d(float(euler[0]), float(euler[1]), float(euler[2])))
            return True
        except Exception:
            return False
