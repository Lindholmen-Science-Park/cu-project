from __future__ import annotations

from typing import Any, Optional

from ..runtime.player_runtime_state import reset_runtime_state


class StageEventWiring:
    """Wires Kit stage OPENED/CLOSED events to runtime state reset."""

    def __init__(self, host: Any):
        self._h = host
        self._stage_subscription: Optional[Any] = None

    def start(self) -> None:
        try:
            import carb.eventdispatcher

            ed = carb.eventdispatcher.get_eventdispatcher()
            self._stage_subscription = ed.observe_event(
                observer_name="younite.usd_viewer_player_core_extension/stage_events",
                event_name="omni.usd@stage_event",
                on_event=self._on_stage_event,
                order=0,
            )
        except Exception as e:
            print(f"[player_core] Failed to subscribe stage events: {e}")
            self._stage_subscription = None

    def stop(self) -> None:
        self._stage_subscription = None

    def _on_stage_event(self, event) -> None:
        """Handle Kit stage events to support scene switching."""
        try:
            import omni.usd

            # Events 2.0 bridge puts the stage event type in the payload;
            # fall back to event.type for Events 1.0 compatibility.
            event_type = None
            try:
                p = getattr(event, "payload", None)
                if p is not None:
                    event_type = p.get("StageEventType")
            except Exception:
                pass
            if event_type is None:
                event_type = getattr(event, "type", None)
            if event_type is None:
                return

            if event_type == int(omni.usd.StageEventType.CLOSED):
                print("[player_core] [STAGE] Stage CLOSED -> resetting player state")
                reset_runtime_state(self._h)
                try:
                    pls = getattr(self._h, "_player_location_service", None)
                    if pls and hasattr(pls, "reset"):
                        pls.reset()
                except Exception:
                    pass

            elif event_type == int(omni.usd.StageEventType.OPENED):
                print("[player_core] [STAGE] Stage OPENED -> ensuring fresh init on readyForPlayer")
                reset_runtime_state(self._h)
                try:
                    pls = getattr(self._h, "_player_location_service", None)
                    if pls and hasattr(pls, "reset"):
                        pls.reset()
                except Exception:
                    pass
        except Exception:
            pass

