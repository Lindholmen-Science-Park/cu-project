"""
Light Culling Extension — entry point.

Listens for ``scene.loaded`` (dispatched by stage_core after the MDL light
init cycle), discovers all UsdLux lights, then starts a 2 Hz async loop
that toggles visibility on the session layer based on player distance.

Web UI toggle: send ``lightCullingToggle`` with ``{"enabled": true/false}``
to enable or disable culling at runtime.  Status is echoed back via
``lightCullingToggleStatus``.
"""

from __future__ import annotations

import omni.ext


class LightCullingExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._scene_loaded_sub = None
        self._manager = None
        self._enabled = False

        self._subscribe_scene_loaded()
        self._subscribe_toggle()
        print("[light_culling] extension started — waiting for scene.loaded")

    # ── Event subscriptions ──────────────────────────────────────────

    def _subscribe_scene_loaded(self) -> None:
        try:
            import carb.eventdispatcher

            ed = carb.eventdispatcher.get_eventdispatcher()
            self._scene_loaded_sub = ed.observe_event(
                observer_name="younite.light_culling_extension/scene_loaded",
                event_name="scene.loaded",
                on_event=self._on_scene_loaded,
                order=0,
            )
        except Exception as e:
            print(f"[light_culling] failed to subscribe scene.loaded: {e}")

    def _subscribe_toggle(self) -> None:
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()

            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("lightCullingToggle"),
                    "lightCullingToggle",
                )
            except Exception:
                pass

            def _on_toggle(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._enabled = bool(payload.get("enabled", not self._enabled))
                print(f"[light_culling] {'enabled' if self._enabled else 'disabled'}")

                if self._manager:
                    if self._enabled:
                        self._manager.start()
                    else:
                        self._manager.stop()

                self._dispatch_status()

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.light_culling_extension/lightCullingToggle",
                    event_name="lightCullingToggle",
                    on_event=_on_toggle,
                    order=0,
                )
            )
        except Exception as e:
            print(f"[light_culling] toggle subscribe failed: {e}")

    # ── scene.loaded handler ─────────────────────────────────────────

    def _on_scene_loaded(self, _event) -> None:
        if self._manager is not None:
            return

        pls = self._get_player_location_service()

        from .light_culling_manager import LightCullingManager

        self._manager = LightCullingManager(player_location_service=pls)
        count = self._manager.discover()
        if count > 0 and self._enabled:
            self._manager.start()
        else:
            print("[light_culling] no lights found or disabled — culling inactive")

        self._dispatch_status()

    # ── Status dispatch ──────────────────────────────────────────────

    def _dispatch_status(self) -> None:
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2("lightCullingToggleStatus", {"enabled": self._enabled})
        except Exception:
            pass

    # ── Player location ──────────────────────────────────────────────

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

    # ── Shutdown ─────────────────────────────────────────────────────

    def on_shutdown(self):
        if self._manager:
            self._manager.stop()
            self._manager = None

        self._scene_loaded_sub = None
        self._subs.clear()
        print("[light_culling] extension shut down")
