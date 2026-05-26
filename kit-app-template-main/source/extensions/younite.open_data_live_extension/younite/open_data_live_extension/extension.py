import omni.ext


def _focus_lat_lon(lat: float, lon: float) -> None:
    """Web list selection: in bird-eye, pan via player_core; else ground teleport.

    Shared between air-quality stations, bike-share docks, and any future IoT lists.
    """
    try:
        import carb
        from younite.messaging_core_extension.message_utils import dispatch_to_events2
        from younite.usd_viewer_stage_core_extension import latlon_to_scene_xyz_for_teleport
        from younite.usd_viewer_stage_core_extension.teleport_registry import get_teleport_service

        x, y_base, z = latlon_to_scene_xyz_for_teleport(lat, lon, 0.0, snap_to_ground=False)

        view_type = str(carb.settings.get_settings().get("/younite/camera/viewType") or "")
        if view_type == "birdEye":
            # player_core handles the pan; do not duplicate the math here.
            dispatch_to_events2("birdEyeRouteClear", {})
            dispatch_to_events2(
                "birdEyePanFocusWorld",
                {"worldPos": [float(x), float(y_base), float(z)]},
            )
            return

        xg, yg, zg = latlon_to_scene_xyz_for_teleport(lat, lon, 0.0)
        ts = get_teleport_service()
        if ts:
            ts.teleport_to_coordinates(xg, yg, zg)
    except Exception:
        pass


class OpenDataLiveExtension(omni.ext.IExt):
    """Dev: IoT air-quality + bike-share + baked OSM POI USD markers + live transit overlay (Västtrafik)."""

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._usd_sub = None
        self._air_svc = None
        self._bike_svc = None
        self._osm_svc = None
        self._transit_svc = None
        self._air_visible = False
        self._bike_visible = False
        self._osm_visible = False
        self._last_osm_stations_for_replay = None
        self._osm_geo_poll_gen = 0

        try:
            import asyncio
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
                normalize_event_payload,
            )

            from .services.air_quality_stations import AirQualityStationsService
            from .services.bike_share_service import BikeShareStationsService
            from .services.osm_poi_markers_service import OsmPoiMarkersService
            from .services.transit_overlay import TransitOverlayService, _vasttrafik_env_creds_ok

            for alias in (
                "iotAirQualityStations",
                "iotAirQualityToggle",
                "iotAirQualityFocusStation",
                "iotAirQualityHighlightStation",
                "iotBikeShareStations",
                "iotBikeShareToggle",
                "iotBikeShareFocusStation",
                "iotBikeShareHighlightStation",
                "iotOsmPoisStations",
                "iotOsmPoisToggle",
                "iotOsmPoisFocusStation",
                "iotOsmPoisHighlightStation",
            ):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(alias), alias)
                except Exception:
                    pass

            self._air_svc = AirQualityStationsService()
            self._bike_svc = BikeShareStationsService()
            self._osm_svc = OsmPoiMarkersService()

            def _notify_transit(payload):
                dispatch_to_events2("transitLiveOverlayStatus", payload)

            self._transit_svc = TransitOverlayService(on_status=_notify_transit)

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _register_station_service(
                alias_prefix: str,
                visible_attr: str,
                get_service,
                *,
                cache_stations_attr: str | None = None,
                after_stations_sync=None,
            ):
                """Wire the four standard {prefix}{Stations,Toggle,FocusStation,HighlightStation}
                events for a service exposing sync_stations / set_group_visible / set_highlight_station_id.

                Used for both air-quality and bike-share; any new IoT marker service can plug in
                with a single call (alias prefix + visibility flag attribute on self).
                """

                def _on_stations(evt):
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    stations = payload.get("stations")
                    if not isinstance(stations, list):
                        return
                    svc = get_service()
                    if not svc:
                        return
                    if cache_stations_attr is not None:
                        setattr(self, cache_stations_attr, list(stations))
                    try:
                        n = svc.sync_stations(stations)
                        visible = n > 0
                        setattr(self, visible_attr, visible)
                        svc.set_group_visible(visible)
                        if after_stations_sync is not None:
                            after_stations_sync(stations, n)
                    except Exception:
                        pass

                def _on_toggle(evt):
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    visible = bool(payload.get("enabled", True))
                    setattr(self, visible_attr, visible)
                    svc = get_service()
                    if not svc:
                        return
                    try:
                        svc.set_group_visible(visible)
                    except Exception:
                        pass

                def _on_focus(evt):
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    try:
                        lat = float(payload.get("lat"))
                        lon = float(payload.get("lon"))
                    except (TypeError, ValueError):
                        return
                    _focus_lat_lon(lat, lon)

                def _on_highlight(evt):
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    raw = payload.get("id")
                    sid = None if raw is None or raw is False else (str(raw).strip() or None)
                    svc = get_service()
                    if not svc:
                        return
                    try:
                        svc.set_highlight_station_id(sid)
                    except Exception:
                        pass

                handlers = (
                    (f"{alias_prefix}Stations", _on_stations),
                    (f"{alias_prefix}Toggle", _on_toggle),
                    (f"{alias_prefix}FocusStation", _on_focus),
                    (f"{alias_prefix}HighlightStation", _on_highlight),
                )
                for event_name, fn in handlers:
                    self._subs.append(
                        ed.observe_event(
                            observer_name=f"younite.open_data_live_extension/{event_name}",
                            event_name=event_name,
                            on_event=fn,
                            order=0,
                        )
                    )

            _register_station_service("iotAirQuality", "_air_visible", lambda: self._air_svc)
            _register_station_service("iotBikeShare", "_bike_visible", lambda: self._bike_svc)

            def _after_osm_stations_sync(stations_list, n: int):
                """GeoCoordinateService loads after MDL wait; first iotOsmPoisStations can arrive too early."""
                if n > 0 or not stations_list:
                    return
                try:
                    from younite.usd_viewer_stage_core_extension import get_geo_coordinate_service

                    g = get_geo_coordinate_service()
                    if g and g.ready:
                        return
                except Exception:
                    pass
                try:
                    self._osm_geo_poll_gen = int(getattr(self, "_osm_geo_poll_gen", 0)) + 1
                    gen = self._osm_geo_poll_gen

                    async def _poll():
                        from younite.usd_viewer_stage_core_extension import get_geo_coordinate_service

                        for _ in range(360):
                            if gen != self._osm_geo_poll_gen:
                                return
                            try:
                                g2 = get_geo_coordinate_service()
                                if g2 and g2.ready and self._osm_svc and gen == self._osm_geo_poll_gen:
                                    cached = getattr(self, "_last_osm_stations_for_replay", None)
                                    if not cached:
                                        return
                                    n2 = self._osm_svc.sync_stations(cached)
                                    self._osm_visible = n2 > 0
                                    self._osm_svc.set_group_visible(n2 > 0)
                                    return
                            except Exception:
                                return
                            try:
                                await kit_app.get_app().next_update_async()
                            except Exception:
                                return

                    asyncio.ensure_future(_poll())
                except Exception:
                    pass

            _register_station_service(
                "iotOsmPois",
                "_osm_visible",
                lambda: self._osm_svc,
                cache_stations_attr="_last_osm_stations_for_replay",
                after_stations_sync=_after_osm_stations_sync,
            )

            def _on_scene_loaded_replay_osm(_evt=None):
                try:
                    from younite.usd_viewer_stage_core_extension import get_geo_coordinate_service

                    cached = getattr(self, "_last_osm_stations_for_replay", None)
                    if not cached or not self._osm_svc:
                        return
                    geo = get_geo_coordinate_service()
                    if not geo or not geo.ready:
                        return
                    n = self._osm_svc.sync_stations(cached)
                    self._osm_visible = n > 0
                    self._osm_svc.set_group_visible(n > 0)
                except Exception:
                    pass

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.open_data_live_extension/scene_loaded_osm_replay",
                    event_name="scene.loaded",
                    on_event=_on_scene_loaded_replay_osm,
                    order=30,
                )
            )

            def _on_transit_request(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                enabled = bool(payload.get("enabled", False))
                api_key = payload.get("apiKey") or payload.get("api_key")
                if self._transit_svc:
                    st = self._transit_svc.set_enabled(enabled, api_key_override=api_key)
                    print(f"[open_data_live] transit overlay enabled={enabled} -> {st}")

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.open_data_live_extension/transitRequest",
                    event_name="transitLiveOverlayRequest",
                    on_event=_on_transit_request,
                    order=0,
                )
            )

            def _on_stage_event(e):
                try:
                    et = int(getattr(e, "type", 0))
                    from omni.usd import StageEventType

                    if et in (int(StageEventType.CLOSED), int(StageEventType.OPENED)):
                        if self._air_svc:
                            self._air_svc.clear()
                        if self._bike_svc:
                            self._bike_svc.clear()
                        if self._osm_svc:
                            self._osm_svc.clear()
                        if self._transit_svc:
                            self._transit_svc.set_enabled(False)
                        self._last_osm_stations_for_replay = None
                        self._osm_geo_poll_gen = int(getattr(self, "_osm_geo_poll_gen", 0)) + 1
                except Exception:
                    pass

            self._usd_sub = ed.observe_event(
                observer_name="younite.open_data_live_extension/stage",
                event_name="omni.usd@stage_event",
                on_event=_on_stage_event,
                order=0,
            )

            async def _announce_transit():
                try:
                    await kit_app.get_app().next_update_async()
                except Exception:
                    pass
                vt_ok = _vasttrafik_env_creds_ok()
                hint = (
                    None
                    if vt_ok
                    else "Set VASTTRAFIK_CLIENT_ID and VASTTRAFIK_CLIENT_SECRET; subscribe app to Travel Planner v4."
                )
                _notify_transit(
                    {
                        "enabled": False,
                        "vehicleCount": 0,
                        "lastError": None,
                        "lastFetchEpochMs": 0,
                        "hasApiKey": vt_ok,
                        "transitSource": "vasttrafik",
                        "vehicles": [],
                        **({"hint": hint} if hint else {}),
                    }
                )

            asyncio.ensure_future(_announce_transit())

            if _vasttrafik_env_creds_ok():
                print(
                    "[open_data_live] Started. Transit overlay off until web enables it. "
                    "With VASTTRAFIK_* set: subscribe the OAuth app to Travel Planner v4 "
                    "or GET /positions returns 403 (900908)."
                )
            else:
                print(
                    "[open_data_live] Started. "
                    "Set VASTTRAFIK_CLIENT_ID and VASTTRAFIK_CLIENT_SECRET for live transit."
                )
        except Exception as e:
            print(f"[open_data_live] startup failed: {e}")

    def on_shutdown(self):
        try:
            if self._transit_svc:
                self._transit_svc.shutdown()
        except Exception:
            pass
        self._transit_svc = None
        self._air_svc = None
        self._bike_svc = None
        self._osm_svc = None
        if getattr(self, "_usd_sub", None):
            self._usd_sub = None
        if getattr(self, "_subs", None):
            self._subs.clear()
        print("[open_data_live] Extension shut down")
