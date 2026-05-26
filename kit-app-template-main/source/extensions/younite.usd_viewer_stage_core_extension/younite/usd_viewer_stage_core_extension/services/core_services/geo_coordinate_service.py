"""
Geospatial coordinate conversion between WGS84 (lat/lon/height) and USD scene coordinates.

Reads the CesiumGeoreferencePrim origin and the CesiumTileset translate from the
stage, then provides bidirectional conversion using a local tangent plane (ENU)
approximation — accurate to <1 m within ~10 km of the origin.

Axis mapping (Y-up scene with metersPerUnit = 0.01):
    East  -> +X
    Up    -> +Y
    North -> -Z

The tileset translate is read automatically so that coordinate conversion matches
any visual alignment adjustments made in Composer.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

_WGS84_A = 6_378_137.0
_WGS84_F = 1.0 / 298.257223563
_WGS84_E2 = 2.0 * _WGS84_F - _WGS84_F * _WGS84_F

_GEOREFERENCE_PRIM_PATH = "/CesiumGeoreference"

_instance: Optional["GeoCoordinateService"] = None


def get_geo_coordinate_service() -> Optional["GeoCoordinateService"]:
    return _instance


def _set_geo_coordinate_service(svc: Optional["GeoCoordinateService"]):
    global _instance
    _instance = svc


class GeoCoordinateService:
    """Lightweight WGS84 <-> USD coordinate converter."""

    def __init__(self):
        self._origin_lat_rad: float = 0.0
        self._origin_lon_rad: float = 0.0
        self._origin_height: float = 0.0
        self._origin_lat_deg: float = 0.0
        self._origin_lon_deg: float = 0.0
        self._scale: float = 100.0
        self._ready: bool = False
        self._subs = []
        self._m_per_deg_lat: float = 0.0
        self._m_per_deg_lon: float = 0.0
        self._tileset_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def origin(self) -> Tuple[float, float, float]:
        return (self._origin_lat_deg, self._origin_lon_deg, self._origin_height)

    def start(self):
        _set_geo_coordinate_service(self)
        self._observe_events()

    def stop(self):
        self._subs.clear()
        _set_geo_coordinate_service(None)

    def load_from_stage(self):
        """Read the CesiumGeoreferencePrim and tileset offset, precompute conversion constants."""
        try:
            import omni.usd
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return False

            self._scale = 1.0 / (stage.GetMetadata("metersPerUnit") or 0.01)

            prim = stage.GetPrimAtPath(_GEOREFERENCE_PRIM_PATH)
            if not prim or not prim.IsValid():
                print("[geo] CesiumGeoreferencePrim not found — coordinate conversion unavailable")
                return False

            lat = prim.GetAttribute("cesium:georeferenceOrigin:latitude").Get()
            lon = prim.GetAttribute("cesium:georeferenceOrigin:longitude").Get()
            height = prim.GetAttribute("cesium:georeferenceOrigin:height").Get()

            if lat is None or lon is None:
                print("[geo] georeference origin attributes missing")
                return False

            self._origin_lat_deg = float(lat)
            self._origin_lon_deg = float(lon)
            self._origin_height = float(height or 0.0)
            self._origin_lat_rad = math.radians(self._origin_lat_deg)
            self._origin_lon_rad = math.radians(self._origin_lon_deg)

            sin_lat = math.sin(self._origin_lat_rad)
            cos_lat = math.cos(self._origin_lat_rad)
            N = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
            self._m_per_deg_lat = math.radians(1.0) * (
                _WGS84_A * (1.0 - _WGS84_E2) / ((1.0 - _WGS84_E2 * sin_lat * sin_lat) ** 1.5)
            )
            self._m_per_deg_lon = math.radians(1.0) * N * cos_lat

            self._tileset_offset = self._read_tileset_offset(stage)

            self._ready = True
            print(
                f"[geo] ready — origin ({self._origin_lat_deg:.6f}, {self._origin_lon_deg:.6f}, "
                f"h={self._origin_height:.1f}m), scale={self._scale}, "
                f"tileset offset=({self._tileset_offset[0]:.1f}, {self._tileset_offset[1]:.1f}, {self._tileset_offset[2]:.1f})"
            )
            return True
        except Exception as e:
            print(f"[geo] failed to read georeference: {e}")
            return False

    def _read_tileset_offset(self, stage) -> Tuple[float, float, float]:
        try:
            from pxr import UsdGeom
            for path in ("/Cesium_World_Terrain",):
                prim = stage.GetPrimAtPath(path)
                if prim and prim.IsValid():
                    xformable = UsdGeom.Xformable(prim)
                    for op in xformable.GetOrderedXformOps():
                        if op.GetOpName() == "xformOp:translate":
                            val = op.Get()
                            if val is not None:
                                return (float(val[0]), float(val[1]), float(val[2]))
        except Exception:
            pass
        return (0.0, 0.0, 0.0)

    def latlon_to_usd(
        self, lat: float, lon: float, height: float = 0.0
    ) -> Optional[Tuple[float, float, float]]:
        if not self._ready:
            return None
        d_lat = lat - self._origin_lat_deg
        d_lon = lon - self._origin_lon_deg
        d_h = height - self._origin_height
        east_m = d_lon * self._m_per_deg_lon
        north_m = d_lat * self._m_per_deg_lat
        up_m = d_h
        ox, oy, oz = self._tileset_offset
        x = east_m * self._scale + ox
        y = up_m * self._scale + oy
        z = -north_m * self._scale + oz
        return (x, y, z)

    def usd_to_latlon(
        self, x: float, y: float, z: float
    ) -> Optional[Tuple[float, float, float]]:
        if not self._ready:
            return None
        ox, oy, oz = self._tileset_offset
        east_m = (x - ox) / self._scale
        up_m = (y - oy) / self._scale
        north_m = -(z - oz) / self._scale
        lat = self._origin_lat_deg + north_m / self._m_per_deg_lat
        lon = self._origin_lon_deg + east_m / self._m_per_deg_lon
        height = self._origin_height + up_m
        return (lat, lon, height)

    def _observe_events(self):
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.stage_core/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            _observe("younite.geo.latlonToUsd", self._on_latlon_to_usd)
            _observe("younite.geo.usdToLatlon", self._on_usd_to_latlon)
        except Exception as e:
            print(f"[geo] event registration failed: {e}")

    def _on_latlon_to_usd(self, event):
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload, dispatch_to_events2,
            )
            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            lat = float(payload.get("lat") or payload.get("latitude") or 0.0)
            lon = float(payload.get("lon") or payload.get("longitude") or 0.0)
            height = float(payload.get("height") or payload.get("altitude") or 0.0)
            request_id = str(payload.get("requestId") or "")
            result = self.latlon_to_usd(lat, lon, height)
            response = {"requestId": request_id, "lat": lat, "lon": lon, "height": height}
            if result:
                response.update({"usd": {"x": result[0], "y": result[1], "z": result[2]}, "success": True})
            else:
                response.update({"success": False, "error": "georeference not ready"})
            dispatch_to_events2("younite.geo.latlonToUsdResult", response)
        except Exception as e:
            print(f"[geo] latlonToUsd error: {e}")

    def _on_usd_to_latlon(self, event):
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload, dispatch_to_events2,
            )
            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            x = float(payload.get("x") or 0.0)
            y = float(payload.get("y") or 0.0)
            z = float(payload.get("z") or 0.0)
            request_id = str(payload.get("requestId") or "")
            result = self.usd_to_latlon(x, y, z)
            response = {"requestId": request_id, "usd": {"x": x, "y": y, "z": z}}
            if result:
                response.update({"lat": result[0], "lon": result[1], "height": result[2], "success": True})
            else:
                response.update({"success": False, "error": "georeference not ready"})
            dispatch_to_events2("younite.geo.usdToLatlonResult", response)
        except Exception as e:
            print(f"[geo] usdToLatlon error: {e}")
