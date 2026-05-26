import omni.ext


class SoundAreaExtension(omni.ext.IExt):
    """Sound area NavMesh feature extension.

    Thin bootstrap — exposes sound_navmesh_areas scripts and syncs
    location names to the web UI on player ready.  Area visibility,
    pathfinding toggles, and cost updates are handled by
    navmesh_route_extension via SoundAreaProvider.
    """

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _alias(name):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass

            def _observe(name, handler):
                _alias(name)
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.sound_area_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            def _on_player_ready(evt):
                try:
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    if bool(payload.get("success", True)):
                        from .scripts.sound_navmesh_areas import get_sound_location_names
                        names = get_sound_location_names()
                        if names:
                            from younite.messaging_core_extension.message_utils import dispatch_to_events2
                            dispatch_to_events2("soundLocationsSync", {
                                "locations": [
                                    {"name": k, "areaName": v}
                                    for k, v in names.items()
                                ],
                            })
                            print(f"[sound_area] Synced {len(names)} sound locations to web")
                except Exception as e:
                    print(f"[sound_area] player ready sync failed: {e}")

            _observe("younite.player.ready", _on_player_ready)

            print("[sound_area] Extension started")

        except Exception as e:
            print(f"[sound_area] subscribe failed: {e}")

    def on_shutdown(self):
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
