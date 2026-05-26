from __future__ import annotations

from typing import Any, Dict, Tuple


def drive_control_state_inputs(character_controller: Any, movement_state: Dict[str, Any]) -> bool:
    """
    Drive omni.physxcct CharacterController via control_state.inputs.

    Supports:
    - keyboard (WASD) in movement_state
    - analog movement_state["forward"/"right"] in [-1..1]

    Returns True if inputs were applied, False otherwise.
    """
    try:
        if not character_controller:
            return False
        control_state = getattr(character_controller, "control_state", None)
        if not control_state or not hasattr(control_state, "inputs"):
            return False

        from omni.physxcct.scripts.utils import ControlAction

        if not isinstance(control_state.inputs, (list, dict)):
            return False

        def set_input(action: int, value: float) -> None:
            if isinstance(control_state.inputs, list):
                while len(control_state.inputs) <= action:
                    control_state.inputs.append(0.0)
                control_state.inputs[action] = float(value)
            else:
                control_state.inputs[action] = float(value)

        # Analog (mobile / point&click): signed values
        if "forward" in movement_state and "right" in movement_state:
            forward_value = float(movement_state.get("forward", 0.0))
            right_value = float(movement_state.get("right", 0.0))
        else:
            forward_value = 0.0
            if movement_state.get("W", False):
                forward_value = 1.0
            elif movement_state.get("S", False):
                forward_value = -1.0
            right_value = 0.0
            if movement_state.get("D", False):
                right_value = 1.0
            elif movement_state.get("A", False):
                right_value = -1.0

        # Resolve ControlAction indices across Kit versions (naming differs).
        # IMPORTANT: In this codebase/build, the working behavior is:
        # - write signed values to FORWARD/RIGHT
        # - keep BACKWARD/LEFT at 0.0
        # (older logic relied on negative FORWARD meaning backward, negative RIGHT meaning left)
        fwd_idx = getattr(ControlAction, "FORWARD", None)
        back_idx = getattr(ControlAction, "BACKWARD", None)
        right_idx = getattr(ControlAction, "RIGHT", None)
        left_idx = getattr(ControlAction, "LEFT", None)
        if any(v is None for v in (fwd_idx, back_idx, right_idx, left_idx)):
            # Unknown ControlAction layout -> let caller fall back to set_move().
            return False

        set_input(int(fwd_idx), float(forward_value))
        set_input(int(back_idx), 0.0)
        set_input(int(right_idx), float(right_value))
        set_input(int(left_idx), 0.0)
        return True
    except Exception:
        return False


def drive_set_move(
    *,
    cct: Any,
    cct_path: str,
    dt: float,
    forward: float,
    right: float,
    speed_multiplier: float,
    base_move_speed: float = 4000.0,
) -> bool:
    """
    Drive PhysX CCT using set_move() (local-space move vector).

    forward/right are in [-1..1] (signed), where +forward means forward.
    """
    try:
        if not cct or not hasattr(cct, "set_move"):
            return False

        f = float(forward)
        r = float(right)
        mag2 = (f * f) + (r * r)
        if mag2 > 1e-8:
            mag = mag2**0.5
            # Normalize to avoid diagonal overspeed
            f /= mag
            r /= mag

        # In this project/build, the working convention has been:
        # move_vec = (forward, right, 0) in local-space delta units.
        # (This matches the previous pre-refactor behavior.)
        move_speed = float(base_move_speed) * float(speed_multiplier)
        move_local = [f * move_speed * float(dt), r * move_speed * float(dt), 0.0]

        try:
            import carb._carb as carb_carb

            move_vec = carb_carb.Float3(move_local[0], move_local[1], move_local[2])
        except Exception:
            move_vec = (move_local[0], move_local[1], move_local[2])

        cct.set_move(str(cct_path), move_vec)
        return True
    except Exception:
        return False

