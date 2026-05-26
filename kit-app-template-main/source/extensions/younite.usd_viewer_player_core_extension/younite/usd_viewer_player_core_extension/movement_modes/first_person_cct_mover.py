from __future__ import annotations

from typing import Any, Dict

from .cct_driver import drive_control_state_inputs


class FirstPersonCctMover:
    """
    First-person manual movement implementation.

    Drives the PhysX CharacterController via `control_state.inputs` only.
    (No fallbacks here — if it can't write control_state.inputs, it does nothing.)
    """

    def __init__(self, *, character_controller: Any):
        self._cc = character_controller

    def drive(self, movement_state: Dict[str, Any]) -> bool:
        return bool(drive_control_state_inputs(self._cc, movement_state))

