from __future__ import annotations

from typing import Any

from younite.usd_viewer_stage_core_extension.services.core_services.world_conventions import PLAYER_CHARACTER_PATH


class JumpController:
    """
    Extracted jump logic + per-frame jump input reset from `extension.py`.

    Mutates the provided host object (PlayerCoreExtension) to preserve current behavior.
    """

    def __init__(self, host: Any):
        self._h = host

    def on_update(self) -> None:
        """If we fired jump via action callback, clear the UP input on next frame."""
        h = self._h
        if hasattr(h, "_reset_jump_next_frame") and h._reset_jump_next_frame:
            try:
                control_state = getattr(h, "_jump_control_state", None)
                if control_state:
                    from omni.physxcct.scripts.utils import ControlAction

                    if hasattr(control_state, "inputs") and isinstance(control_state.inputs, (list, dict)):
                        control_action_up = ControlAction.UP
                        if isinstance(control_state.inputs, list) and len(control_state.inputs) > control_action_up:
                            control_state.inputs[control_action_up] = 0.0
                        elif isinstance(control_state.inputs, dict):
                            control_state.inputs[control_action_up] = 0.0
                h._reset_jump_next_frame = False
                h._jump_control_state = None
            except Exception:
                h._reset_jump_next_frame = False
                h._jump_control_state = None

    def jump(self) -> bool:
        h = self._h
        character_controller = getattr(h, "_nv_character_controller", None)
        if not character_controller:
            print("[JUMP] ❌ CharacterController instance not available")
            return False

        cct = getattr(h, "_nv_cct_interface", None)
        cct_path = getattr(h, "_player_character_path", PLAYER_CHARACTER_PATH)
        if cct:
            try:
                if hasattr(cct, "enable_gravity"):
                    cct.enable_gravity(str(cct_path))
            except Exception as e:
                print(f"[JUMP] ⚠️ Could not enable gravity: {e}")

        try:
            control_state = getattr(character_controller, "control_state", None)
            if control_state is None:
                print("[JUMP] ⚠️ control_state is None, attempting to initialize via setup_controls()...")
                if hasattr(character_controller, "setup_controls"):
                    try:
                        character_controller.setup_controls(500.0)
                        control_state = getattr(character_controller, "control_state", None)
                        if control_state is None:
                            print("[JUMP] ❌ control_state still None after setup_controls()")
                            return False
                        print("[JUMP] ✓ control_state initialized via setup_controls()")
                    except Exception as e:
                        print(f"[JUMP] ❌ setup_controls() failed: {e}")
                        return False
                else:
                    print("[JUMP] ❌ CharacterController has no setup_controls() method")
                    return False

            if hasattr(control_state, "action_callbacks"):
                action_callbacks = control_state.action_callbacks
                if isinstance(action_callbacks, dict) and "CctMoveUp" in action_callbacks:
                    try:
                        callback = action_callbacks["CctMoveUp"]
                        if callable(callback):
                            import carb.input as ci

                            class DummyKeyboardEvent:
                                def __init__(self):
                                    self.type = ci.KeyboardEventType.KEY_PRESS
                                    self.input = ci.KeyboardInput.SPACE
                                    self.flags = ci.BUTTON_FLAG_PRESSED
                                    self.value = 1.0

                            evt = DummyKeyboardEvent()
                            callback(evt)

                            if not hasattr(h, "_reset_jump_next_frame"):
                                h._reset_jump_next_frame = False
                            h._reset_jump_next_frame = True
                            h._jump_control_state = control_state
                            return True
                    except Exception as e:
                        print(f"[JUMP] ❌ action_callbacks['CctMoveUp'](evt) failed: {e}")
                        import traceback

                        traceback.print_exc()
                        return False

            print("[JUMP] ❌ Could not find 'CctMoveUp' in action_callbacks")
            if hasattr(control_state, "action_callbacks"):
                try:
                    print(
                        f"[JUMP] 💡 Available action_callbacks keys: {list(control_state.action_callbacks.keys()) if isinstance(control_state.action_callbacks, dict) else 'N/A'}"
                    )
                except Exception:
                    pass
            return False

        except Exception as e:
            print(f"[JUMP] ❌ Error setting control_state.up: {e}")
            import traceback

            traceback.print_exc()
            return False

