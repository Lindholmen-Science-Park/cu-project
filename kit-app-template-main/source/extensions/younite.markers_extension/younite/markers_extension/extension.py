import omni.ext


class MarkersExtension(omni.ext.IExt):
    """Marker placement feature (toggle + consume pick results)."""

    MARKERS_ENABLED_SETTING = "/younite/markers/enabled"

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._enabled = False
        try:
            import carb.settings as carb_settings
            self._settings = carb_settings.get_settings()
        except Exception:
            self._settings = None

        from .marker_placement_service import MarkerPlacementService
        self._marker_service = MarkerPlacementService()

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.markers_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            def _on_toggle(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._enabled = bool(payload.get("enabled", False))
                print(f"[markers] marker placement {'enabled' if self._enabled else 'disabled'}")
                try:
                    if self._settings:
                        self._settings.set(self.MARKERS_ENABLED_SETTING, bool(self._enabled))
                except Exception:
                    pass

            def _on_pick_result(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                if not self._enabled:
                    return
                if str(payload.get("intent") or "") not in ("marker", "marker.place", "markerPlacement"):
                    return
                hit = payload.get("hit")
                if hit and isinstance(hit, dict) and hit.get("world"):
                    w = hit["world"]
                    try:
                        pos = (float(w.get("x")), float(w.get("y")), float(w.get("z")))
                        normal = None
                        n = hit.get("normal")
                        if isinstance(n, dict):
                            normal = (float(n.get("x")), float(n.get("y")), float(n.get("z")))
                        self._marker_service.place_marker(pos, normal)
                    except Exception as e:
                        print(f"[markers] marker placement failed: {e}")

            _observe("markerPlacementToggle", _on_toggle)
            _observe("younite.pick.result", _on_pick_result)
        except Exception as e:
            print(f"[markers] subscribe failed: {e}")

    def on_shutdown(self):
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._marker_service = None
        self._settings = None

