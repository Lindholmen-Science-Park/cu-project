import omni.ext
import omni.usd

from .osm_graph_service import OsmGraphService
from . import osm_route_drawer

_OSM_ROADS_PRIM = "/World/OSM_Roads"
_SRC = "osm_navigation"


class OsmNavigationExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._target_poi_id: str | None = None
        self._graph = OsmGraphService()

        self._poi_scene_coords: dict[str, tuple[float, float, float]] = {}
        self._pois_loaded = False

        self._map_visible = False

        # Current movement mode for dev City Navigate. Production CU
        # routes do not reach this extension — they go through
        # RouteComposer which reads its own mode from NavMeshModeCache.
        self._mode: str = "walking"
        # Last pick XZ so a mode toggle can recompute without a re-pick.
        self._last_click_xz: tuple[float, float] | None = None

        self._subscribe()

        print("[OSM Nav] Extension started (graph deferred)")

    def _ensure_graph(self) -> bool:
        """Lazy-load the road graph on first use."""
        if self._graph.is_loaded:
            return True
        self._graph.load()
        return self._graph.is_loaded

    # ------------------------------------------------------------------
    # Roads activation — prim is active=false in USD, activated on demand
    # ------------------------------------------------------------------

    def _set_roads_active(self, active: bool):
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            prim = stage.GetPrimAtPath(_OSM_ROADS_PRIM)
            if not prim or not prim.IsValid():
                return
            prim.SetActive(active)
        except Exception as e:
            print(f"[OSM Nav] Failed to {'activate' if active else 'deactivate'} roads: {e}")

    # ------------------------------------------------------------------
    # POI loading (from geo_data json, same source as geo_poi_extension)
    # ------------------------------------------------------------------

    def _load_pois(self):
        """Load POI lat/lon from example_geo_data.json and convert to scene
        coords using the GeoCoordinateService."""
        import json
        from pathlib import Path

        probe = Path(__file__).resolve()
        geo_json = None
        for _ in range(10):
            candidate = probe / "source" / "data" / "geo_layer" / "example_geo_data.json"
            if candidate.is_file():
                geo_json = candidate
                break
            if probe.name == "kit-app-template-main":
                candidate = probe / "source" / "data" / "geo_layer" / "example_geo_data.json"
                if candidate.is_file():
                    geo_json = candidate
                    break
            parent = probe.parent
            if parent == probe:
                break
            probe = parent

        if not geo_json:
            print("[OSM Nav] Could not find example_geo_data.json")
            return

        try:
            from younite.usd_viewer_stage_core_extension import get_geo_coordinate_service

            geo = get_geo_coordinate_service()
            if not geo or not geo.ready:
                print("[OSM Nav] GeoCoordinateService not ready — cannot convert POIs")
                return

            with open(geo_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            for poi in data.get("pois", []):
                pid = poi.get("id")
                lat = poi.get("lat")
                lon = poi.get("lon")
                if pid and lat and lon:
                    result = geo.latlon_to_usd(lat, lon, 0.0)
                    if result:
                        self._poi_scene_coords[pid] = result
                        print(f"[OSM Nav] POI '{pid}' at scene ({result[0]:.0f}, {result[1]:.0f}, {result[2]:.0f})")

            if self._poi_scene_coords:
                self._pois_loaded = True
                print(f"[OSM Nav] {len(self._poi_scene_coords)} POIs loaded")
        except Exception as e:
            print(f"[OSM Nav] Failed to load POIs: {e}")

    # ------------------------------------------------------------------
    # Event subscriptions
    # ------------------------------------------------------------------

    def _subscribe(self):
        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
                register_outbound_events,
            )

            register_outbound_events(["osmRouteResult"])

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(name), name
                    )
                except Exception:
                    pass
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.osm_navigation_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            def _on_set_poi(evt):
                payload = normalize_event_payload(
                    getattr(evt, "payload", None) or {}
                )
                self._ensure_graph()
                if not self._pois_loaded:
                    self._load_pois()
                poi_id = payload.get("poiId")
                if poi_id and poi_id in self._poi_scene_coords:
                    self._target_poi_id = poi_id
                    print(f"[OSM Nav] Target POI set to '{poi_id}'")
                else:
                    print(f"[OSM Nav] Unknown POI '{poi_id}', "
                          f"available: {list(self._poi_scene_coords.keys())}")

            def _on_clear(evt):
                self._target_poi_id = None
                self._mode = "walking"
                self._last_click_xz = None
                stage = omni.usd.get_context().get_stage()
                if stage:
                    osm_route_drawer.clear_route(stage)
                if self._map_visible:
                    self._map_visible = False
                    self._set_roads_active(False)
                print("[OSM Nav] Route cleared")

            def _on_set_mode(evt):
                payload = normalize_event_payload(
                    getattr(evt, "payload", None) or {}
                )
                mode = str(payload.get("mode") or "walking")
                if mode not in OsmGraphService.available_modes():
                    print(f"[OSM Nav] Unknown mode '{mode}' — "
                          f"available: {OsmGraphService.available_modes()}")
                    return
                self._mode = mode
                print(f"[OSM Nav] Mode set to '{mode}'")
                # Recompute current route (if any) with the new mode.
                if self._last_click_xz and self._target_poi_id:
                    sx, sz = self._last_click_xz
                    self._calculate_route(sx, sz)

            def _on_toggle_map(evt):
                payload = normalize_event_payload(
                    getattr(evt, "payload", None) or {}
                )
                visible = bool(payload.get("visible", not self._map_visible))
                self._map_visible = visible
                self._set_roads_active(visible)
                print(f"[OSM Nav] Road map {'activated' if visible else 'deactivated'}")

            def _on_pick_result(evt):
                payload = normalize_event_payload(
                    getattr(evt, "payload", None) or {}
                )
                intent = str(payload.get("intent") or "")
                if intent != "osmNavigate":
                    return
                if not self._target_poi_id:
                    print("[OSM Nav] No target POI set, ignoring pick")
                    return

                hit = payload.get("hit")
                if not hit or not isinstance(hit, dict) or not hit.get("world"):
                    return

                w = hit["world"]
                try:
                    sx = float(w.get("x"))
                    sz = float(w.get("z"))
                except (TypeError, ValueError):
                    return

                self._calculate_route(sx, sz)

            _observe("osmNavigateSetPoi", _on_set_poi)
            _observe("osmNavigateClear", _on_clear)
            _observe("osmNavigateToggleMap", _on_toggle_map)
            _observe("osmNavigateSetMode", _on_set_mode)
            _observe("younite.pick.result", _on_pick_result)

        except Exception as e:
            print(f"[OSM Nav] subscribe failed: {e}")

    # ------------------------------------------------------------------
    # OSM_Roads prim offset (the prim may be translated in the sublayer)
    # ------------------------------------------------------------------

    def _get_roads_offset(self) -> tuple[float, float, float]:
        """Read the translate on /World/OSM_Roads so graph coords map to world coords."""
        try:
            from pxr import UsdGeom
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return (0.0, 0.0, 0.0)
            prim = stage.GetPrimAtPath(_OSM_ROADS_PRIM)
            if not prim or not prim.IsValid():
                return (0.0, 0.0, 0.0)
            xform = UsdGeom.Xformable(prim)
            for op in xform.GetOrderedXformOps():
                if op.GetOpName() == "xformOp:translate":
                    t = op.Get()
                    return (float(t[0]), float(t[1]), float(t[2]))
        except Exception:
            pass
        return (0.0, 0.0, 0.0)

    # ------------------------------------------------------------------
    # Route calculation
    # ------------------------------------------------------------------

    def _calculate_route(self, start_x: float, start_z: float):
        if not self._ensure_graph() or not self._target_poi_id:
            return

        # Stash every pick so a later mode-toggle can recompute without
        # forcing the user to re-click on the map.
        self._last_click_xz = (start_x, start_z)

        dest = self._poi_scene_coords.get(self._target_poi_id)
        if not dest:
            return

        dest_x, _, dest_z = dest

        ox, _, oz = self._get_roads_offset()

        mode = self._mode
        start_node = self._graph.nearest_node(
            start_x - ox, start_z - oz, mode=mode
        )
        end_node = self._graph.nearest_node(dest_x, dest_z, mode=mode)

        if not start_node or not end_node:
            print(f"[OSM Nav] Could not find {mode}-reachable nodes near start/end")
            self._send_result(False, 0, 0)
            return

        path, dist_cm = self._graph.shortest_path(start_node, end_node, mode=mode)

        if not path:
            print(f"[OSM Nav] No {mode} path found")
            self._send_result(False, 0, 0)
            return

        coords = self._graph.path_to_coords(path)
        shifted = [(x + ox, y, z + oz) for x, y, z in coords]
        dist_m = dist_cm / 100.0
        time_s = self._graph.estimate_walk_time(dist_cm)

        stage = omni.usd.get_context().get_stage()
        if stage:
            osm_route_drawer.draw_route(stage, shifted)

        print(f"[OSM Nav] Route ({mode}): {len(path)} nodes, "
              f"{dist_m:.0f} m, ~{time_s:.0f} s walk "
              f"(offset: {ox:.0f}, {oz:.0f})")

        self._send_result(True, dist_m, time_s)

    def _send_result(self, success: bool, distance_m: float, time_s: float):
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2
            dispatch_to_events2("osmRouteResult", {
                "success": success,
                "distanceMeters": round(distance_m, 1),
                "estimatedTimeSeconds": round(time_s, 1),
                "poiId": self._target_poi_id or "",
            })
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def on_shutdown(self):
        self._subs.clear()

        stage = omni.usd.get_context().get_stage()
        if stage:
            osm_route_drawer.clear_route(stage)

        print("[OSM Nav] Extension shut down")
