from __future__ import annotations

import time
from typing import List, Optional, Tuple

from .ease_helpers import apply_exponential_coast


class TouchLookHandler:
    """
    Consumes ``touchLookDelta`` / ``touchLookEnd`` from the web stream viewport.

    First-person: drag look + post-release coast on camera yaw/pitch.
    Bird-eye: drag pan + brief post-release coast (forward/right analog).
    """

    ACTIVE_TIMEOUT_S: float = 0.15

    # First-person look coast (higher decay = shorter glide)
    COAST_DECAY_PER_SEC: float = 12.0
    COAST_STOP_VEL: float = 0.25

    # Bird-eye map pan coast — very short (higher decay = shorter glide)
    BIRD_EYE_COAST_DECAY_PER_SEC: float = 95.0
    BIRD_EYE_COAST_STOP_VEL: float = 0.18

    def __init__(self, *, sensitivity: float = 0.15):
        self._sensitivity = float(sensitivity)
        self._delta_yaw = 0.0
        self._delta_pitch = 0.0
        self._subs: List[object] = []
        self._last_delta_time: float = 0.0

        self._coast_vel_yaw: float = 0.0
        self._coast_vel_pitch: float = 0.0
        self._coast_armed: bool = False

        self._be_coast_forward: float = 0.0
        self._be_coast_right: float = 0.0
        self._be_coast_armed: bool = False

    def start(self) -> None:
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _register_alias(name: str) -> None:
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(name),
                        name,
                    )
                except Exception:
                    pass

            _register_alias("touchLookDelta")
            _register_alias("touchLookEnd")

            def _on_touch_look_delta(evt):
                try:
                    from younite.messaging_core_extension.message_utils import normalize_event_payload

                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    dx = float(payload.get("dx", 0.0))
                    dy = float(payload.get("dy", 0.0))
                    self._delta_yaw += -dx * self._sensitivity
                    self._delta_pitch += dy * self._sensitivity
                    self._last_delta_time = time.monotonic()
                    if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                        self._coast_armed = False
                        self._be_coast_armed = False
                        self._clear_fp_coast()
                        self._clear_be_coast()
                except Exception:
                    pass

            def _on_touch_look_end(_evt):
                self._coast_armed = True
                self._be_coast_armed = True

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.usd_viewer_player_core_extension/touchLookDelta",
                    event_name="touchLookDelta",
                    on_event=_on_touch_look_delta,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.usd_viewer_player_core_extension/touchLookEnd",
                    event_name="touchLookEnd",
                    on_event=_on_touch_look_end,
                    order=0,
                )
            )
        except Exception as e:
            print(f"[player_core] touchLookDelta subscription failed: {e}")
            self._subs = []

    def stop(self) -> None:
        self._subs = []
        self._clear_fp_coast()
        self._clear_be_coast()
        self._coast_armed = False
        self._be_coast_armed = False

    def _clear_fp_coast(self) -> None:
        self._coast_vel_yaw = 0.0
        self._coast_vel_pitch = 0.0

    def _clear_be_coast(self) -> None:
        self._be_coast_forward = 0.0
        self._be_coast_right = 0.0

    def is_coasting(self) -> bool:
        return self._coast_armed and (
            abs(self._coast_vel_yaw) > self.COAST_STOP_VEL
            or abs(self._coast_vel_pitch) > self.COAST_STOP_VEL
        )

    def is_bird_eye_coasting(self) -> bool:
        return self._be_coast_armed and (
            abs(self._be_coast_forward) > self.BIRD_EYE_COAST_STOP_VEL
            or abs(self._be_coast_right) > self.BIRD_EYE_COAST_STOP_VEL
        )

    def is_active(self) -> bool:
        if self._last_delta_time == 0.0:
            return self.is_coasting() or self.is_bird_eye_coasting()
        dragging = (time.monotonic() - self._last_delta_time) < self.ACTIVE_TIMEOUT_S
        return dragging or self.is_coasting() or self.is_bird_eye_coasting()

    def tick(self, dt: float) -> Tuple[float, float]:
        """First-person look: drag + short release coast."""
        dt = max(float(dt or 0.0), 1.0 / 240.0)
        drag_yaw = float(self._delta_yaw)
        drag_pitch = float(self._delta_pitch)
        self._delta_yaw = 0.0
        self._delta_pitch = 0.0

        if abs(drag_yaw) > 1e-6 or abs(drag_pitch) > 1e-6:
            self._coast_vel_yaw = drag_yaw / dt
            self._coast_vel_pitch = drag_pitch / dt
            return drag_yaw, drag_pitch

        if not self._coast_armed:
            return 0.0, 0.0

        cy, self._coast_vel_yaw, active_y = apply_exponential_coast(
            self._coast_vel_yaw,
            dt,
            decay_per_sec=self.COAST_DECAY_PER_SEC,
            stop_vel=self.COAST_STOP_VEL,
        )
        cp, self._coast_vel_pitch, active_p = apply_exponential_coast(
            self._coast_vel_pitch,
            dt,
            decay_per_sec=self.COAST_DECAY_PER_SEC,
            stop_vel=self.COAST_STOP_VEL,
        )
        if not (active_y or active_p):
            self._coast_armed = False
        return cy, cp

    def tick_bird_eye_pan(self, dt: float) -> Tuple[float, float]:
        """
        Bird-eye map pan: returns (forward, right) analog for movement_state.
        Sign flip to grab-the-world is applied in PlayerInputController.
        """
        dt = max(float(dt or 0.0), 1.0 / 240.0)
        drag_forward = float(self._delta_pitch)
        drag_right = float(self._delta_yaw)
        self._delta_yaw = 0.0
        self._delta_pitch = 0.0

        if abs(drag_forward) > 1e-6 or abs(drag_right) > 1e-6:
            self._be_coast_forward = drag_forward / dt
            self._be_coast_right = drag_right / dt
            return drag_forward, drag_right

        if not self._be_coast_armed:
            return 0.0, 0.0

        cf, self._be_coast_forward, active_f = apply_exponential_coast(
            self._be_coast_forward,
            dt,
            decay_per_sec=self.BIRD_EYE_COAST_DECAY_PER_SEC,
            stop_vel=self.BIRD_EYE_COAST_STOP_VEL,
        )
        cr, self._be_coast_right, active_r = apply_exponential_coast(
            self._be_coast_right,
            dt,
            decay_per_sec=self.BIRD_EYE_COAST_DECAY_PER_SEC,
            stop_vel=self.BIRD_EYE_COAST_STOP_VEL,
        )
        if not (active_f or active_r):
            self._be_coast_armed = False
        return cf, cr
