from __future__ import annotations

from typing import Any, Optional


class BirdEyeZoomService:
    """Web-driven zoom for the bird-eye view.

    Overrides ``focalLength`` on the player camera's session layer while
    in bird-eye view. Pinch on mobile / scroll wheel on desktop drives
    the zoom level; this service applies the override and restores the
    original focal length when the user leaves bird-eye view.

    Same session-layer pattern as :class:`ResolutionService`'s portrait
    FOV cap (which edits aperture rather than focalLength, so the two
    coexist without fighting). The framer pitch animation is independent
    too — it edits the camera's local RotateXYZ op, not lens attrs.

    Zoom level convention:
      - ``1.0`` = no zoom (uses authored ``focalLength``)
      - ``> 1.0`` = zoomed in (longer focal length, narrower FOV)
      - clamped to ``[MIN_LEVEL, MAX_LEVEL]``
    """

    MIN_LEVEL: float = 1.0
    MAX_LEVEL: float = 4.0

    def __init__(self, host: Any):
        self._h = host
        self._original_focal: Optional[float] = None
        self._current_level: float = 1.0
        self._cam_path_cache: Optional[str] = None

    def _camera_path(self) -> Optional[str]:
        h = self._h
        try:
            return getattr(h, "_camera_path", None) or (
                f"{getattr(h, '_player_character_path', '/World/PlayerCharacter')}/first_person_camera"
            )
        except Exception:
            return None

    def _is_bird_eye(self) -> bool:
        try:
            return str(getattr(self._h, "_camera_view_type", "firstPerson") or "firstPerson") == "birdEye"
        except Exception:
            return False

    def get_zoom_level(self) -> float:
        return float(self._current_level)

    def set_zoom_level(self, level: float) -> bool:
        """Apply a new zoom level. No-op when not in bird-eye view."""
        if not self._is_bird_eye():
            return False
        try:
            level = max(float(self.MIN_LEVEL), min(float(self.MAX_LEVEL), float(level)))
        except (TypeError, ValueError):
            return False

        try:
            import omni.usd
            from pxr import UsdGeom, Usd

            cam_path = self._camera_path()
            if not cam_path:
                return False
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return False
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if not (cam_prim and cam_prim.IsValid()):
                return False
            camera = UsdGeom.Camera(cam_prim)

            if self._original_focal is None:
                # Read original from the strongest non-session opinion if
                # possible; fall back to the resolved attr value.
                try:
                    self._original_focal = float(camera.GetFocalLengthAttr().Get() or 18.0)
                except Exception:
                    self._original_focal = 18.0
                self._cam_path_cache = str(cam_path)

            new_focal = float(self._original_focal) * float(level)

            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, Usd.EditTarget(session)):
                if abs(level - 1.0) < 1e-3:
                    camera.GetFocalLengthAttr().Clear()
                else:
                    camera.GetFocalLengthAttr().Set(float(new_focal))
            self._current_level = float(level)
            return True
        except Exception:
            return False

    def snap_restore(self) -> None:
        """Clear any session-layer focal length override (used on view switch)."""
        try:
            import omni.usd
            from pxr import UsdGeom, Usd

            cam_path = self._cam_path_cache or self._camera_path()
            if not cam_path:
                return
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if not (cam_prim and cam_prim.IsValid()):
                return
            camera = UsdGeom.Camera(cam_prim)
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, Usd.EditTarget(session)):
                try:
                    camera.GetFocalLengthAttr().Clear()
                except Exception:
                    pass
        except Exception:
            pass
        self._original_focal = None
        self._current_level = 1.0
        self._cam_path_cache = None
