from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import omni.appwindow
import carb.input as ci


class KeyboardMouseInput:
    """
    Desktop input provider:
    - Keyboard: WASD + Q/E (yaw)
    - Mouse: RMB capture + mouse delta for look
    - Space: jump callback

    This class is intentionally *only* input capture/state.
    View-angle state + camera prim application live in `PlayerInputController`.
    """

    def __init__(self, *, on_jump: Optional[Callable[[], bool]] = None):
        self._on_jump = on_jump

        self._input_enabled = True

        self._moving: Dict[str, bool] = {"W": False, "A": False, "S": False, "D": False, "Q": False, "E": False}

        self._mouse_sensitivity = 0.1
        self._mouse_delta = [0.0, 0.0]  # [dx, dy] accumulated since last consume

        self._keyboard = None
        self._mouse = None
        self._input = None
        self._kbd_sub_id = None
        self._mouse_sub_id = None

        self._setup_keyboard_input()
        self._setup_mouse_input()

    def set_input_enabled(self, enabled: bool) -> None:
        self._input_enabled = bool(enabled)
        if self._input_enabled:
            for k in self._moving:
                self._moving[k] = False

    def get_movement_state(self) -> Dict[str, bool]:
        """Digital movement keys only (W/A/S/D/Q/E)."""
        return dict(self._moving)

    def consume_mouse_delta(self) -> Tuple[float, float]:
        """Returns (dx, dy) scaled by sensitivity, then resets."""
        dx, dy = float(self._mouse_delta[0]), float(self._mouse_delta[1])
        self._mouse_delta = [0.0, 0.0]
        return dx, dy

    def on_shutdown(self) -> None:
        if self._input and self._keyboard and self._kbd_sub_id is not None:
            try:
                if hasattr(self._input, "unsubscribe_from_keyboard_events"):
                    self._input.unsubscribe_from_keyboard_events(self._keyboard, self._kbd_sub_id)
                elif hasattr(self._input, "unsubscribe"):
                    self._input.unsubscribe(self._kbd_sub_id)
            except Exception:
                pass
        self._kbd_sub_id = None

        if self._input and self._mouse and self._mouse_sub_id is not None:
            try:
                if hasattr(self._input, "unsubscribe_from_mouse_events"):
                    self._input.unsubscribe_from_mouse_events(self._mouse, self._mouse_sub_id)
                elif hasattr(self._input, "unsubscribe"):
                    self._input.unsubscribe(self._mouse_sub_id)
            except Exception:
                pass
        self._mouse_sub_id = None

    def _setup_keyboard_input(self) -> None:
        try:
            win = omni.appwindow.get_default_app_window()
            self._keyboard = win.get_keyboard()
            self._input = ci.acquire_input_interface()
            self._kbd_sub_id = self._input.subscribe_to_keyboard_events(self._keyboard, self._on_keyboard_event)
        except Exception:
            self._keyboard = None
            self._input = None
            self._kbd_sub_id = None

    def _setup_mouse_input(self) -> None:
        try:
            win = omni.appwindow.get_default_app_window()
            self._mouse = win.get_mouse()
            if self._input and self._mouse:
                try:
                    self._mouse_sub_id = self._input.subscribe_to_mouse_events(self._mouse, self._on_mouse_event)
                except Exception:
                    self._mouse_sub_id = None
        except Exception:
            self._mouse = None
            self._mouse_sub_id = None

    def _on_mouse_event(self, e: ci.MouseEvent):
        """Accumulate mouse deltas for look. Scroll and RMB are disabled (handled by viewport_safety)."""
        if not self._input:
            return 0
        # Right/middle mouse and scroll are disabled for streaming: point-and-click / touch look only.
        # Swallow so viewport never gets them; camera bindings also disable these gestures.
        try:
            if e.type in (
                ci.MouseEventType.RIGHT_BUTTON_DOWN,
                ci.MouseEventType.RIGHT_BUTTON_UP,
                ci.MouseEventType.MIDDLE_BUTTON_DOWN,
                ci.MouseEventType.MIDDLE_BUTTON_UP,
            ):
                return 0
            if getattr(ci.MouseEventType, "SCROLL", None) is not None and e.type == getattr(ci.MouseEventType, "SCROLL", -1):
                return 0
        except Exception:
            pass

        try:
            if (
                self._input_enabled
                and e.type == ci.MouseEventType.MOVE
                and hasattr(e, "mouse_delta_x")
                and hasattr(e, "mouse_delta_y")
            ):
                self._mouse_delta = [
                    float(e.mouse_delta_x) * float(self._mouse_sensitivity),
                    float(e.mouse_delta_y) * float(self._mouse_sensitivity),
                ]
        except Exception:
            pass
        return 0

    def _on_keyboard_event(self, e: ci.KeyboardEvent):
        if not self._input:
            return 0

        if not self._input_enabled:
            # still allow ESC to release pointer lock if captured
            if hasattr(ci.KeyboardInput, "ESCAPE") and e.input == ci.KeyboardInput.ESCAPE:
                if e.type == ci.KeyboardEventType.KEY_PRESS:
                    try:
                        import omni.kit.viewport.utility as vp_utils

                        vp = vp_utils.get_active_viewport()
                        if vp and hasattr(vp, "set_mouse_capture"):
                            vp.set_mouse_capture(False)
                    except Exception:
                        pass
                return 0
            return 0

        # Space triggers jump immediately (not part of movement_state)
        if e.input == ci.KeyboardInput.SPACE:
            if e.type == ci.KeyboardEventType.KEY_PRESS:
                try:
                    if callable(self._on_jump):
                        self._on_jump()
                except Exception:
                    pass
                # Preserve previous behavior: avoid stray strafe on jump press.
                self._moving["A"] = False
                self._moving["D"] = False
            return 0

        # ESC releases pointer lock if captured
        if hasattr(ci.KeyboardInput, "ESCAPE") and e.input == ci.KeyboardInput.ESCAPE:
            if e.type == ci.KeyboardEventType.KEY_PRESS:
                try:
                    import omni.kit.viewport.utility as vp_utils

                    vp = vp_utils.get_active_viewport()
                    if vp and hasattr(vp, "set_mouse_capture"):
                        vp.set_mouse_capture(False)
                except Exception:
                    pass
            return 0

        def _is_input(inp, names):
            for n in names:
                if hasattr(ci.KeyboardInput, n) and inp == getattr(ci.KeyboardInput, n):
                    return True
            return False

        key = None
        if _is_input(e.input, ["W", "KEY_W", "LetterW", "LETTER_W"]):
            key = "W"
        elif _is_input(e.input, ["A", "KEY_A", "LetterA", "LETTER_A"]):
            key = "A"
        elif _is_input(e.input, ["S", "KEY_S", "LetterS", "LETTER_S"]):
            key = "S"
        elif _is_input(e.input, ["D", "KEY_D", "LetterD", "LETTER_D"]):
            key = "D"
        elif _is_input(e.input, ["Q", "KEY_Q", "LetterQ", "LETTER_Q"]):
            key = "Q"
        elif _is_input(e.input, ["E", "KEY_E", "LetterE", "LETTER_E"]):
            key = "E"

        if key is None:
            return 0

        if e.type in (ci.KeyboardEventType.KEY_PRESS, ci.KeyboardEventType.KEY_REPEAT):
            self._moving[key] = True
        elif e.type == ci.KeyboardEventType.KEY_RELEASE:
            self._moving[key] = False
        return 0

