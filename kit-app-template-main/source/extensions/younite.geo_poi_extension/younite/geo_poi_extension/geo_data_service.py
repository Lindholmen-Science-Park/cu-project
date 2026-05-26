"""
Geo Data Service - Dynamically creates POI markers from JSON data.

Uses GeoCoordinateService for WGS84 -> USD coordinate conversion.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import omni.usd
from pxr import UsdGeom, Gf

from younite.payload_orchestrator_core_extension import show_hide, batch_show_hide, Priority


class GeoDataService:
    """Service for loading and visualizing geo-referenced POI data."""

    def __init__(self):
        self._pois_parent_path = "/World/POIs"
        self._loaded_pois: Dict[str, str] = {}

    def _convert_latlon(self, lat: float, lon: float, height_offset: float = 0.0):
        try:
            from younite.usd_viewer_stage_core_extension import get_geo_coordinate_service

            geo = get_geo_coordinate_service()
            if geo and geo.ready:
                return geo.latlon_to_usd(lat, lon, height_offset)
        except Exception:
            pass
        return None

    def load_geo_data(self, json_path: str) -> Optional[Dict[str, Any]]:
        """Load POI data from a JSON file."""
        try:
            json_file = Path(json_path)
            if not json_file.exists():
                print(f"[GEO_DATA] JSON file not found: {json_path}")
                return None

            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            print(f"[GEO_DATA] Loaded geo data from {json_path}")
            return data
        except Exception as e:
            print(f"[GEO_DATA] Error loading geo data: {e}")
            return None

    def create_poi_marker(
        self,
        poi_id: str,
        name: str,
        lat: float,
        lon: float,
        color: List[float] = [1.0, 0.0, 0.0],
        height_offset: float = 0.0,
    ) -> Optional[str]:
        """Create a vertical pole marker for a POI."""
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                print("[GEO_DATA] No stage available")
                return None

            coords = self._convert_latlon(lat, lon, height_offset)
            if not coords:
                print(f"[GEO_DATA] Cannot convert lat/lon for '{name}' — GeoCoordinateService not ready")
                return None

            x, y, z = coords
            print(f"[GEO_DATA] POI '{name}': ({lat:.6f}, {lon:.6f}) -> USD ({x:.1f}, {y:.1f}, {z:.1f})")

            pois_parent = stage.GetPrimAtPath(self._pois_parent_path)
            if not pois_parent or not pois_parent.IsValid():
                world_prim = stage.GetPrimAtPath("/World")
                if not world_prim or not world_prim.IsValid():
                    print("[GEO_DATA] /World prim not found")
                    return None
                UsdGeom.Xform.Define(stage, self._pois_parent_path)

            poi_path = f"{self._pois_parent_path}/{poi_id}"

            existing_prim = stage.GetPrimAtPath(poi_path)
            if existing_prim and existing_prim.IsValid():
                stage.RemovePrim(poi_path)

            poi_xform = UsdGeom.Xform.Define(stage, poi_path)
            if not poi_xform:
                return None

            xformable = UsdGeom.Xformable(poi_xform)
            xformable.ClearXformOpOrder()
            translate_op = xformable.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
            translate_op.Set(Gf.Vec3d(x, y, z))

            prim = stage.GetPrimAtPath(poi_path)
            prim.SetCustomDataByKey("geo:lat", str(lat))
            prim.SetCustomDataByKey("geo:lon", str(lon))
            prim.SetCustomDataByKey("geo:name", name)
            prim.SetCustomDataByKey("geo:id", poi_id)

            DEFAULT_POLE_HEIGHT = 50000.0
            DEFAULT_POLE_SIZE = 500.0

            pole_path = f"{poi_path}/MarkerPole"
            pole_box = UsdGeom.Cube.Define(stage, pole_path)
            if pole_box:
                pole_box.GetSizeAttr().Set(DEFAULT_POLE_SIZE)
                pole_xform = UsdGeom.Xformable(pole_box)
                pole_xform.ClearXformOpOrder()
                scale_op = pole_xform.AddScaleOp(UsdGeom.XformOp.PrecisionDouble)
                scale_y = DEFAULT_POLE_HEIGHT / DEFAULT_POLE_SIZE
                scale_op.Set(Gf.Vec3d(1.0, scale_y, 1.0))

                pole_prim = stage.GetPrimAtPath(pole_path)
                if pole_prim:
                    from pxr import Sdf
                    try:
                        display_color_attr = pole_prim.CreateAttribute("primvars:displayColor", Sdf.ValueTypeNames.Color3fArray)
                        if display_color_attr:
                            display_color_attr.Set([Gf.Vec3f(float(color[0]), float(color[1]), float(color[2]))])
                    except Exception as e:
                        print(f"[GEO_DATA] Could not set display color: {e}")

                show_hide(pole_path, True, source="geo_poi")

            show_hide(poi_path, False, source="geo_poi")

            self._loaded_pois[poi_id] = poi_path
            print(f"[GEO_DATA] Created POI '{name}' at ({x:.1f}, {y:.1f}, {z:.1f})")
            return poi_path
        except Exception as e:
            print(f"[GEO_DATA] Error creating POI marker: {e}")
            return None

    def load_and_create_pois(self, json_path: str, plane_height: float = 50.0) -> bool:
        """Load POI data from JSON and create all markers."""
        _ = plane_height
        data = self.load_geo_data(json_path)
        if not data:
            return False

        pois = data.get("pois", [])
        if not pois:
            print("[GEO_DATA] No POIs found in data file")
            return False

        success_count = 0
        for poi_data in pois:
            if not poi_data.get("enabled", True):
                continue
            poi_id = poi_data.get("id")
            if not poi_id:
                continue
            marker_path = self.create_poi_marker(
                poi_id=poi_id,
                name=poi_data.get("name", poi_id),
                lat=poi_data.get("lat"),
                lon=poi_data.get("lon"),
                color=poi_data.get("color", [1.0, 0.0, 0.0]),
                height_offset=0.0,
            )
            if marker_path:
                success_count += 1

        print(f"[GEO_DATA] Created {success_count}/{len(pois)} POI markers")
        return success_count > 0

    def set_poi_markers_visible(self, visible: bool) -> bool:
        try:
            items = [(path, visible) for path in self._loaded_pois.values()]
            batch_show_hide(items, source="geo_poi", group="poi_visibility")
            print(f"[GEO_DATA] POI markers {'shown' if visible else 'hidden'}")
            return True
        except Exception as e:
            print(f"[GEO_DATA] Error toggling POI visibility: {e}")
            return False

    def clear_pois(self):
        if not self._loaded_pois:
            return
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            for _poi_id, poi_path in self._loaded_pois.items():
                prim = stage.GetPrimAtPath(poi_path)
                if prim and prim.IsValid():
                    stage.RemovePrim(poi_path)
            count = len(self._loaded_pois)
            self._loaded_pois.clear()
            print(f"[GEO_DATA] Cleared {count} POI markers")
        except Exception as e:
            print(f"[GEO_DATA] Error clearing POIs: {e}")
