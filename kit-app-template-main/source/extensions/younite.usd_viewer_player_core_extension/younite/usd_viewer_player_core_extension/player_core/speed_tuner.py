from __future__ import annotations

from typing import Any


BASE_CCT_SPEED = 500.0


class MovementSpeedTuner:
    """
    Applies the UI speed slider to CCT (WASD / joystick) movement.

    The PhysX CharacterController reads ``control_state.speed`` each physics
    step to compute movement distance.  We simply update that value —
    calling ``setup_controls()`` again would destroy input bindings.
    """

    def __init__(self, host: Any):
        self._h = host

    def set_movement_speed(self, speed_multiplier: float) -> bool:
        h = self._h
        try:
            h._movement_speed_multiplier = max(0.1, min(10.0, float(speed_multiplier)))

            cc = getattr(h, "_nv_character_controller", None)
            cs = getattr(cc, "control_state", None) if cc else None
            if cs is not None:
                cs.speed = BASE_CCT_SPEED * h._movement_speed_multiplier

            print(f"[SPEED] multiplier {h._movement_speed_multiplier}x")
            return True
        except Exception as e:
            print(f"[SPEED] Error setting movement speed: {e}")
            return False

