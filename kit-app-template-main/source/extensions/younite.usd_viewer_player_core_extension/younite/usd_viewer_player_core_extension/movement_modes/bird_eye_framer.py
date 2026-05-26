from __future__ import annotations

import time
from typing import Any, Optional


class BirdEyeFramer:
    """Cinematic camera tilt for the bird-eye view.

    When the bird-eye Directions / POI sheet opens, the bottom sheet hides
    the player marker (and often the destination). This service animates an
    extra downward pitch on the player's camera (`first_person_camera`'s
    local RotateXYZ X component) so the player position pulls visually
    upward on screen, ending up above the bottom sheet. After the
    animation completes, manual drag-pan stays free so the user can browse
    the route to inspect the whole path.

    On dismiss, the same pitch is animated back to its original value.
    On view-type switch / teleport, state is snapped back without
    animation (the teleport service zeros out the camera local rotation
    anyway, so there is nothing left to undo).
    """

    # Negative = tilt camera further DOWN. The sign is flipped relative to a
    # naive right-hand-rule guess because the parent player body's combined
    # XYZ rotation (≈ 159°, -45°, 180° at the bird-eye spawn) inverts the
    # effective direction of a positive rotation on the camera's local X axis.
    #
    # Magnitude tuning: more tilt-down pulls the player marker further UP
    # on screen toward center (good for clearing the panel), but past ~20°
    # it starts to feel like a top-down map and you lose the cinematic
    # bird-eye perspective. ~15° puts the player marker just above the
    # bottom-sheet top edge while keeping the original framing feel.
    TILT_DELTA_DEG: float = -15.0
    ANIM_DURATION_S: float = 0.45

    def __init__(self, host: Any):
        self._h = host

        self._original_pitch_deg: Optional[float] = None

        self._anim_from_deg: Optional[float] = None
        self._anim_to_deg: Optional[float] = None
        self._anim_start_t: Optional[float] = None

        self._framed: bool = False

    def is_framed(self) -> bool:
        return self._framed

    def is_animating(self) -> bool:
        return self._anim_start_t is not None

    def _camera_path(self) -> Optional[str]:
        h = self._h
        try:
            return getattr(h, "_camera_path", None) or (
                f"{getattr(h, '_player_character_path', '/World/PlayerCharacter')}/first_person_camera"
            )
        except Exception:
            return None

    def _read_pitch_deg(self) -> Optional[float]:
        try:
            import omni.usd
            from pxr import UsdGeom

            cam_path = self._camera_path()
            if not cam_path:
                return None
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return None
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if not (cam_prim and cam_prim.IsValid()):
                return None
            cam_xf = UsdGeom.Xformable(cam_prim)
            rot_op = cam_xf.GetRotateXYZOp()
            if rot_op:
                rot = rot_op.Get()
                if rot is not None:
                    return float(rot[0])
            return 0.0
        except Exception:
            return None

    def _write_pitch_deg(self, pitch_deg: float) -> bool:
        try:
            import omni.usd
            from pxr import UsdGeom, Gf

            cam_path = self._camera_path()
            if not cam_path:
                return False
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return False
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if not (cam_prim and cam_prim.IsValid()):
                return False
            cam_xf = UsdGeom.Xformable(cam_prim)
            rot_op = cam_xf.GetRotateXYZOp()
            if not rot_op:
                rot_op = cam_xf.AddRotateXYZOp()
            # Preserve Y/Z so we don't clobber any active bird-eye yaw
            # written by ``BirdEyeYawService`` (which owns the Z component).
            cur = rot_op.Get()
            y = float(cur[1]) if cur is not None else 0.0
            z = float(cur[2]) if cur is not None else 0.0
            rot_op.Set(Gf.Vec3d(float(pitch_deg), y, z))
            return True
        except Exception:
            return False

    def frame(self) -> bool:
        """Begin the tilt-down animation. No-op unless we are in bird-eye view."""
        h = self._h
        try:
            view_type = str(getattr(h, "_camera_view_type", "firstPerson") or "firstPerson")
        except Exception:
            view_type = "firstPerson"
        if view_type != "birdEye":
            return False

        cur = self._read_pitch_deg()
        if cur is None:
            return False

        if self._original_pitch_deg is None:
            self._original_pitch_deg = float(cur)

        self._anim_from_deg = float(cur)
        self._anim_to_deg = float(self._original_pitch_deg) + float(self.TILT_DELTA_DEG)
        self._anim_start_t = time.monotonic()
        self._framed = True
        return True

    def restore(self) -> bool:
        """Animate back to the original pitch. No-op if we never framed."""
        if self._original_pitch_deg is None:
            self._framed = False
            return False
        cur = self._read_pitch_deg()
        if cur is None:
            self.snap_restore()
            return False
        self._anim_from_deg = float(cur)
        self._anim_to_deg = float(self._original_pitch_deg)
        self._anim_start_t = time.monotonic()
        return True

    def snap_restore(self) -> None:
        """Immediately reset (used on teleport / view switch)."""
        if self._original_pitch_deg is not None:
            self._write_pitch_deg(float(self._original_pitch_deg))
        self._original_pitch_deg = None
        self._anim_from_deg = None
        self._anim_to_deg = None
        self._anim_start_t = None
        self._framed = False

    def update(self, dt: float) -> None:
        if (
            self._anim_start_t is None
            or self._anim_from_deg is None
            or self._anim_to_deg is None
        ):
            return
        try:
            now = time.monotonic()
            elapsed = now - self._anim_start_t
            tt = max(0.0, min(1.0, elapsed / float(self.ANIM_DURATION_S)))
            ease = tt * tt * (3.0 - 2.0 * tt)
            cur = self._anim_from_deg + (self._anim_to_deg - self._anim_from_deg) * ease
            self._write_pitch_deg(cur)
            if tt >= 1.0:
                finished_to = self._anim_to_deg
                self._anim_from_deg = None
                self._anim_to_deg = None
                self._anim_start_t = None
                if (
                    self._original_pitch_deg is not None
                    and abs(finished_to - float(self._original_pitch_deg)) < 1e-3
                ):
                    self._original_pitch_deg = None
                    self._framed = False
        except Exception:
            self._anim_from_deg = None
            self._anim_to_deg = None
            self._anim_start_t = None
