from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class WebJoystickInput:
    """
    Mobile/web joystick state.

    - `set_move(forward, right)`: left joystick analog move (-1..1)
    - `set_look(yaw, pitch)`: right joystick analog look (-1..1)
    """

    move_deadzone: float = 0.1
    look_deadzone: float = 0.1
    look_pitch_max_deg: float = 15.0

    _forward: float = 0.0
    _right: float = 0.0
    _look_yaw: float = 0.0
    _look_pitch: float = 0.0

    def set_move(self, forward: float, right: float) -> None:
        self._forward = max(-1.0, min(1.0, float(forward)))
        self._right = max(-1.0, min(1.0, float(right)))

    def set_look(self, yaw: float, pitch: float) -> None:
        self._look_yaw = max(-1.0, min(1.0, float(yaw)))
        self._look_pitch = max(-1.0, min(1.0, float(pitch)))

    def get_move(self) -> Tuple[float, float, bool]:
        f, r = float(self._forward), float(self._right)
        active = abs(f) > float(self.move_deadzone) or abs(r) > float(self.move_deadzone)
        return f, r, bool(active)

    def get_look(self) -> Tuple[float, float, bool]:
        yaw, pitch = float(self._look_yaw), float(self._look_pitch)
        active = abs(yaw) > float(self.look_deadzone) or abs(pitch) > float(self.look_deadzone)
        return yaw, pitch, bool(active)

