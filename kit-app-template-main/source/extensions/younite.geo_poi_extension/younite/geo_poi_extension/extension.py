import omni.ext


class GeoPoiExtension(omni.ext.IExt):
    """Geo-referenced POI markers feature (GeoDataService split)."""

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._usd_sub = None
        self._tasks = []
        self._enabled = False
        self._svc = None
        self._loaded = False

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import normalize_event_payload
            from .geo_data_service import GeoDataService
            import omni.usd

            ed = carb.eventdispatcher.get_eventdispatcher()
            try:
                kit_app.register_event_alias(carb.events.type_from_string("poiMarkersToggle"), "poiMarkersToggle")
            except Exception:
                pass

            self._svc = GeoDataService()

            def _find_source_data_dir():
                try:
                    from pathlib import Path

                    probe = Path(__file__).resolve()
                    for _ in range(10):
                        if probe.name == "source" and (probe / "data").exists():
                            return probe / "data"
                        data_dir = probe / "data"
                        if data_dir.exists() and (data_dir / "geo_layer").exists():
                            return data_dir
                        if probe.name == "kit-app-template-main" and (probe / "source" / "data").exists():
                            return probe / "source" / "data"
                        parent = probe.parent
                        if parent == probe:
                            break
                        probe = parent
                except Exception:
                    pass
                return None

            def _default_geo_json_path():
                data_dir = _find_source_data_dir()
                if not data_dir:
                    return None
                geo_json_path = data_dir / "geo_layer" / "example_geo_data.json"
                return geo_json_path if geo_json_path.exists() else None

            async def _try_load_geo():
                try:
                    # Wait one frame to ensure stage is fully available
                    await kit_app.get_app().next_update_async()
                except Exception:
                    pass
                try:
                    if not self._svc:
                        return
                    stage = omni.usd.get_context().get_stage()
                    if not stage:
                        return
                    geo_json = _default_geo_json_path()
                    if not geo_json:
                        print("[geo_poi] [GEO_DATA] ⚠️ Geo data file not found (expected source/data/geo_layer/example_geo_data.json)")
                        return
                    print(f"[geo_poi] [GEO_DATA] Loading POI data from {geo_json}")
                    self._loaded = bool(self._svc.load_and_create_pois(str(geo_json), plane_height=50.0))
                    # Apply current enabled state after load
                    if self._loaded:
                        try:
                            self._svc.set_poi_markers_visible(bool(self._enabled))
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[geo_poi] [GEO_DATA] ⚠️ Error loading geo data: {e}")
                    try:
                        import traceback
                        traceback.print_exc()
                    except Exception:
                        pass

            def _schedule_load():
                try:
                    import asyncio

                    t = asyncio.ensure_future(_try_load_geo())
                    self._tasks.append(t)
                except Exception:
                    pass

            def _on_toggle(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._enabled = bool(payload.get("enabled", True))
                print(f"[geo_poi] POI markers {'enabled' if self._enabled else 'disabled'}")
                try:
                    if self._svc:
                        # If enabling and we haven't loaded yet (e.g. started late), load now.
                        if self._enabled and not self._loaded:
                            _schedule_load()
                        self._svc.set_poi_markers_visible(self._enabled)
                except Exception:
                    pass

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.geo_poi_extension/poiMarkersToggle",
                    event_name="poiMarkersToggle",
                    on_event=_on_toggle,
                    order=0,
                )
            )

            # Handle scene switches (extensions stay enabled across stage opens).
            try:
                import carb.eventdispatcher

                def _on_stage_event(e):
                    try:
                        et = int(getattr(e, "type", 0))
                        from omni.usd import StageEventType

                        if et == int(StageEventType.CLOSED):
                            self._loaded = False
                            if self._svc:
                                self._svc.clear_pois()
                        elif et == int(StageEventType.OPENED):
                            self._loaded = False
                            if self._svc:
                                self._svc.clear_pois()
                    except Exception:
                        pass

                ed = carb.eventdispatcher.get_eventdispatcher()
                self._usd_sub = ed.observe_event(
                    observer_name="younite.geo_poi_extension/stage_events",
                    event_name="omni.usd@stage_event",
                    on_event=_on_stage_event,
                    order=0,
                )
            except Exception as e:
                print(f"[geo_poi] stage event subscribe failed: {e}")

            # Intentionally no initial load: we lazy-load on first enable toggle.
        except Exception as e:
            print(f"[geo_poi] subscribe failed: {e}")

    def on_shutdown(self):
        try:
            for t in getattr(self, "_tasks", []) or []:
                try:
                    if hasattr(t, "cancel"):
                        t.cancel()
                except Exception:
                    pass
        except Exception:
            pass
        self._tasks = []

        if getattr(self, "_usd_sub", None):
            self._usd_sub = None

        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._svc = None
        self._loaded = False

