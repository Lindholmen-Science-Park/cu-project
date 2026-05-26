"""
Tile Management Extension — entry point.

Listens for ``scene.loaded``, discovers city tile prims, then manages them
via a hybrid culling strategy (distance in first-person, frustum in bird's
eye) routed through the Payload Orchestrator.

Starts **disabled** by default.  Web UI toggle: ``tileCullingToggle``
with ``{"enabled": true/false}``.
"""

from __future__ import annotations

import omni.ext


class DistanceCullingExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._scene_loaded_sub = None
        self._manager = None
        self._enabled = False

        self._subscribe_scene_loaded()
        self._subscribe_toggle()

    def _subscribe_scene_loaded(self) -> None:
        try:
            import carb.eventdispatcher
            self._scene_loaded_sub = carb.eventdispatcher.get_eventdispatcher().observe_event(
                observer_name="younite.distance_culling_extension/scene_loaded",
                event_name="scene.loaded",
                on_event=self._on_scene_loaded,
                order=0,
            )
        except Exception:
            pass

    def _subscribe_toggle(self) -> None:
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("tileCullingToggle"),
                    "tileCullingToggle",
                )
            except Exception:
                pass

            def _on_toggle(evt):
                payload = normalize_event_payload(
                    getattr(evt, "payload", None) or {})
                self._enabled = bool(payload.get("enabled", not self._enabled))

                if self._manager:
                    if self._enabled:
                        self._manager.start()
                    else:
                        self._manager.stop()
                self._dispatch_status()

            self._subs.append(
                carb.eventdispatcher.get_eventdispatcher().observe_event(
                    observer_name="younite.distance_culling_extension/tileCullingToggle",
                    event_name="tileCullingToggle",
                    on_event=_on_toggle,
                    order=0,
                )
            )
        except Exception:
            pass

    def _on_scene_loaded(self, _event) -> None:
        if self._manager is not None:
            return

        from .tile_manager import TileManager

        self._manager = TileManager(
            player_location_service=self._get_player_location_service())
        count = self._manager.discover()

        if count > 0 and self._enabled:
            self._manager.start()

        self._dispatch_status()

    def _dispatch_status(self) -> None:
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2
            dispatch_to_events2("tileCullingToggleStatus", {"enabled": self._enabled})
        except Exception:
            pass

    @staticmethod
    def _get_player_location_service():
        try:
            from younite.usd_viewer_player_core_extension import extension as _pc
            instance = getattr(_pc, "_instance", None)
            if instance:
                return instance.get_player_location_service()
        except Exception:
            pass
        return None

    def on_shutdown(self):
        if self._manager:
            self._manager.stop()
            self._manager = None
        self._scene_loaded_sub = None
        self._subs.clear()
