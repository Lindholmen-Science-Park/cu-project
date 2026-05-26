"""
Incoming message bridge (WebRTC/web client -> Events 2.0 semantic events).

omni.kit.livestream.messaging wraps incoming messages into a single wrapper event
("omni.kit.livestream.receive_message" or "customEvent") with payload:
  { event_type: "<semantic>", payload: {...} }

This module observes wrapper events once and re-dispatches the semantic event type
into Events 2.0 so other parts can observe by name.
"""

from __future__ import annotations

from typing import List, Optional


class IncomingMessageBridge:
    def __init__(self, *, wrapper_events: Optional[list[str]] = None):
        self._subs: List[object] = []
        self._wrapper_events = wrapper_events or [
            "omni.kit.livestream.receive_message",
            "customEvent",
        ]

    def start(self) -> None:
        from ...message_utils import extract_event_from_message, dispatch_to_events2
        import carb.eventdispatcher
        import omni.kit.app as kit_app
        import carb

        ed = carb.eventdispatcher.get_eventdispatcher()

        def _handle_incoming_message(evt):
            try:
                payload = getattr(evt, "payload", {}) or {}
                result = extract_event_from_message(payload)
                if result:
                    evt_type, clean_payload = result
                    dispatch_to_events2(evt_type, clean_payload)
            except Exception:
                # keep behavior: ignore malformed messages
                pass

        for wrapper_event in self._wrapper_events:
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string(wrapper_event),
                    wrapper_event,
                )
                obs = ed.observe_event(
                    observer_name=f"younite.messaging_core_extension/messaging_bridge/{wrapper_event}",
                    event_name=wrapper_event,
                    on_event=_handle_incoming_message,
                    order=0,
                )
                self._subs.append(obs)
            except Exception:
                pass

    def stop(self) -> None:
        self._subs.clear()

