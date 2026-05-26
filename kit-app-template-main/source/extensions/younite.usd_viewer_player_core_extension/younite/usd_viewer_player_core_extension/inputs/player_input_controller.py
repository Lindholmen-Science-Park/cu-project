from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from .desktop import KeyboardMouseInput
from .mobile import WebJoystickInput
from .point_click import TouchLookHandler


class PlayerInputController:
    """
    Aggregates multiple input sources into the legacy `movement_state` dict:
    - Desktop: W/A/S/D (+ Q/E for yaw), mouse look, Space jump
    - Mobile: web joystick move (forward/right), web joystick look (yaw/pitch)
    - Touch look: hold+drag on stream viewport (touchLookDelta events)
    - Bird's-eye touch drag: in bird-eye view, touch drag drives XZ movement instead of camera rotation

    Exposes `get_view_angles`/`set_view_angles` so movement modes (bird-eye, point&click)
    can keep operating without knowing about input sources.
    """

    def __init__(
        self,
        *,
        movement_callback: Optional[Callable[[float, Dict[str, Any]], None]] = None,
        jump_callback: Optional[Callable[[], bool]] = None,
        get_camera_path: Optional[Callable[[], Optional[str]]] = None,
        get_view_type: Optional[Callable[[], str]] = None,
        mobile_joystick: Optional[WebJoystickInput] = None,
        touch_look: Optional[TouchLookHandler] = None,
    ):
        self._movement_callback = movement_callback
        self._get_camera_path = get_camera_path
        self._get_view_type = get_view_type

        self._desktop = KeyboardMouseInput(on_jump=jump_callback)
        self._mobile = mobile_joystick or WebJoystickInput()
        self._touch_look = touch_look

        self._input_enabled = True

        # View angles (degrees). Shared across all modes.
        self._yaw = 0.0
        self._pitch = 0.0
        self._pitch_min = -89.0
        self._pitch_max = 89.0

        # Desktop yaw from Q/E (kept as previous behavior: per-frame step, not dt-scaled)
        self._qe_yaw_step = 1.6

    @property
    def mobile_joystick(self) -> WebJoystickInput:
        return self._mobile

    def set_input_enabled(self, enabled: bool) -> None:
        self._input_enabled = bool(enabled)
        self._desktop.set_input_enabled(self._input_enabled)
        if not self._input_enabled:
            # Keep view angles; just stop applying deltas.
            pass

    def on_shutdown(self) -> None:
        try:
            self._desktop.on_shutdown()
        except Exception:
            pass

    def _is_bird_eye(self) -> bool:
        try:
            if callable(self._get_view_type):
                return str(self._get_view_type()) == "birdEye"
        except Exception:
            pass
        return False

    def update(self, dt: float) -> None:
        """
        Called each frame by `PlayerUpdateLoop`.
        - Builds movement_state (digital keys + optional analog forward/right)
        - In bird-eye view: converts touch-drag deltas into XZ movement instead of camera rotation
        - Calls movement_callback(dt, movement_state)
        - Applies view yaw/pitch to camera prim (mouse/QE + mobile look)
        """
        dt = float(dt or 0.0) or (1.0 / 60.0)

        movement_state: Dict[str, Any] = self._desktop.get_movement_state()

        # Prefer mobile analog move when active.
        f, r, mobile_move_active = self._mobile.get_move()
        if self._input_enabled and mobile_move_active:
            movement_state["forward"] = float(f)
            movement_state["right"] = float(r)
        else:
            movement_state.pop("forward", None)
            movement_state.pop("right", None)

        # Bird's-eye touch drag: consume touch deltas as XZ movement.
        # In bird-eye view the camera angle is locked, so drag = pan, not look.
        bird_eye_touch_active = False
        if self._input_enabled and self._is_bird_eye() and self._touch_look:
            pan_f, pan_r = self._touch_look.tick_bird_eye_pan(dt)
            if (
                abs(pan_f) > 1e-6
                or abs(pan_r) > 1e-6
                or (
                    hasattr(self._touch_look, "is_bird_eye_coasting")
                    and self._touch_look.is_bird_eye_coasting()
                )
            ):
                bird_eye_touch_active = True
                movement_state["forward"] = -float(pan_f)
                movement_state["right"] = -float(pan_r)
                movement_state["_bird_eye_touch_drag"] = True

        if self._movement_callback:
            try:
                self._movement_callback(float(dt), movement_state)
            except Exception:
                pass

        # Apply view (mouse + Q/E + mobile look) to camera prim
        if not self._input_enabled:
            return

        # In bird-eye mode the camera angle is locked — consume but discard
        # mouse/touch deltas so they don't accumulate for when the user
        # switches back to first-person.
        if self._is_bird_eye():
            self._desktop.consume_mouse_delta()
            return

        try:
            dx, dy = self._desktop.consume_mouse_delta()

            # Keyboard rotation (Q/E) affects yaw.
            if movement_state.get("Q", False):
                self._yaw += float(self._qe_yaw_step)
            if movement_state.get("E", False):
                self._yaw += -float(self._qe_yaw_step)

            # Mouse delta
            self._yaw += float(dx)
            self._pitch += -float(dy)
            self._pitch = max(self._pitch_min, min(self._pitch_max, float(self._pitch)))

            # Mobile look joystick deltas
            lj_yaw, lj_pitch, mobile_look_active = self._mobile.get_look()
            if mobile_look_active:
                yaw_sens = 1.2
                pitch_sens = 1.0
                self._yaw += float(lj_yaw) * float(yaw_sens)
                self._pitch += float(lj_pitch) * float(pitch_sens)
                pmax = float(getattr(self._mobile, "look_pitch_max_deg", 15.0))
                self._pitch = max(-pmax, min(pmax, float(self._pitch)))

            # Touch look (hold+drag + post-release coast on stream viewport).
            touch_look_active = False
            if self._touch_look and not bird_eye_touch_active:
                t_yaw, t_pitch = self._touch_look.tick(dt)
                if abs(t_yaw) > 1e-6 or abs(t_pitch) > 1e-6:
                    touch_look_active = True
                    self._yaw += float(t_yaw)
                    self._pitch += -float(t_pitch)
                    self._pitch = max(self._pitch_min, min(self._pitch_max, float(self._pitch)))
            coasting = (
                self._touch_look
                and not bird_eye_touch_active
                and hasattr(self._touch_look, "is_coasting")
                and self._touch_look.is_coasting()
            )
            if (
                dx == 0.0
                and dy == 0.0
                and not movement_state.get("Q", False)
                and not movement_state.get("E", False)
                and not mobile_look_active
                and not touch_look_active
                and not coasting
            ):
                return

            cam_path = None
            try:
                if callable(self._get_camera_path):
                    cam_path = self._get_camera_path()
            except Exception:
                cam_path = None
            if not cam_path:
                return

            import omni.usd
            from pxr import UsdGeom, Gf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            cam_prim = stage.GetPrimAtPath(str(cam_path))
            if not (cam_prim and cam_prim.IsValid()):
                return

            xform = UsdGeom.Xformable(cam_prim)
            rot_op = xform.GetRotateXYZOp()
            if not rot_op:
                rot_op = xform.AddRotateXYZOp()
            rot_op.Set(Gf.Vec3d(float(self._pitch), float(self._yaw), 0.0))
        except Exception:
            pass

    def reset_rotation_state(self) -> None:
        self._yaw = 0.0
        self._pitch = 0.0

    def get_view_angles(self) -> Tuple[float, float]:
        return float(self._yaw), float(self._pitch)

    def set_view_angles(self, yaw_deg: float, pitch_deg: Optional[float] = None) -> None:
        try:
            self._yaw = float(yaw_deg)
        except Exception:
            pass
        if pitch_deg is not None:
            try:
                self._pitch = float(pitch_deg)
            except Exception:
                pass

    def set_player_controller(self, pc: Any) -> None:
        """
        Called by physx_bootstrap after camera path is set on the host.
        Camera path is read via get_camera_path() from the host; this exists so bootstrap can call it without error.
        """
        pass

