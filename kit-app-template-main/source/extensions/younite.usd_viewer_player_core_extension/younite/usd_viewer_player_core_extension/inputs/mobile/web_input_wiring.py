from __future__ import annotations

from typing import Optional

from .web_joystick_input import WebJoystickInput


class WebInputWiring:
    """Wires web/mobile joystick events into `WebJoystickInput`."""

    def __init__(self, *, joystick: WebJoystickInput):
        self._joystick = joystick
        self._joystick_sub: Optional[object] = None
        self._look_input_sub: Optional[object] = None

    def start(self) -> None:
        # Joystick input from web (mobile view)
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()
            try:
                kit_app.register_event_alias(carb.events.type_from_string("joystickInput"), "joystickInput")
            except Exception:
                pass

            def _on_joystick_input(evt):
                try:
                    payload = getattr(evt, "payload", None) or {}
                    forward = float(payload.get("forward", 0.0))
                    right = float(payload.get("right", 0.0))
                    self._joystick.set_move(forward, right)
                except Exception:
                    pass

            self._joystick_sub = ed.observe_event(
                observer_name="younite.usd_viewer_player_core_extension/joystickInput",
                event_name="joystickInput",
                on_event=_on_joystick_input,
                order=0,
            )
        except Exception as e:
            print(f"[player_core] joystickInput subscription failed: {e}")
            self._joystick_sub = None

        # Look joystick input from web (right joystick - mobile view)
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()
            try:
                kit_app.register_event_alias(carb.events.type_from_string("lookInput"), "lookInput")
            except Exception:
                pass

            def _on_look_input(evt):
                try:
                    payload = getattr(evt, "payload", None) or {}
                    yaw = float(payload.get("yaw", 0.0))
                    pitch = float(payload.get("pitch", 0.0))
                    self._joystick.set_look(yaw, pitch)
                except Exception:
                    pass

            self._look_input_sub = ed.observe_event(
                observer_name="younite.usd_viewer_player_core_extension/lookInput",
                event_name="lookInput",
                on_event=_on_look_input,
                order=0,
            )
        except Exception as e:
            print(f"[player_core] lookInput subscription failed: {e}")
            self._look_input_sub = None

    def stop(self) -> None:
        for sub_name in ("_joystick_sub", "_look_input_sub"):
            setattr(self, sub_name, None)

