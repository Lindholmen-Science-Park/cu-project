"""
Runtime OpenStreetMap POI markers under /World/IoT_OsmPois/Stations.

Baked JSON from ``source/data/osm/export_osm_pois.py``; web sends one category at a time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import omni.usd
from pxr import Gf, UsdGeom

from younite.payload_orchestrator_core_extension import Priority, batch_show_hide, show_hide

from .air_quality_stations import (
    _ANCHOR_BEACON_LIFT_CM,
    _POLE_AND_BEACON_RGB,
    _bind_material,
    _make_preview_emissive_material,
    _sanitize_id,
    _set_preview_mat_colors,
)

STATIONS_ROOT = "/World/IoT_OsmPois/Stations"
STATIONS_GROUP = "/World/IoT_OsmPois"
SOURCE = "open_data_live"


def _ensure_stations_root(stage) -> bool:
    """Create marker parent chain if the sublayer is missing from the composed stage."""
    try:
        world = stage.GetPrimAtPath("/World")
        if not world or not world.IsValid():
            return False
        grp = stage.GetPrimAtPath(STATIONS_GROUP)
        if not grp or not grp.IsValid():
            UsdGeom.Xform.Define(stage, STATIONS_GROUP)
        parent = stage.GetPrimAtPath(STATIONS_ROOT)
        if not parent or not parent.IsValid():
            UsdGeom.Scope.Define(stage, STATIONS_ROOT)
        p = stage.GetPrimAtPath(STATIONS_ROOT)
        return bool(p and p.IsValid())
    except Exception:
        return False

# Many OSM points at once: keep pole + crown small so markers do not overlap into soup.
# (Air/bike use tall poles + large halos for sparse stations; different UX.)
_OSM_POLE_HEIGHT_CM = 3200.0  # 32 m
_OSM_POLE_RADIUS_CM = 140.0  # 1.4 m radius
_OSM_HALO_RADIUS_CM = 380.0  # 3.8 m crown — was 32 m equivalent at 3200 radius
_OSM_BEACON_RADIUS_CM = 110.0
_OSM_HALO_EMISSIVE = 1.35
_OSM_HALO_OPACITY = 0.4
_OSM_BEACON_EMISSIVE = 3.2

# Default crowns: one vivid family on stream (category tint + grey beacon read as muddy brown).
_UNSEL_HALO_RGB = (0.96, 0.34, 0.06)
_UNSEL_BEACON_RGB = (0.9, 0.22, 0.05)
# When a list row is selected, other markers stay readable but recede.
_UNSEL_HALO_DIM_RGB = (0.55, 0.22, 0.07)
_UNSEL_BEACON_DIM_RGB = (0.5, 0.16, 0.05)

# Selected: warm halo vs cooler beacon (lower emissive on beacon avoids RTX blowing to white).
_SELECT_HALO_RGB = (0.99, 0.5, 0.04)
_SELECT_BEACON_RGB = (0.02, 0.48, 0.55)


def _path_to_station_id(station_path: str) -> str:
    parts = str(station_path or "").rstrip("/").split("/")
    return parts[-1] if parts else ""


class OsmPoiMarkersService:
    def __init__(self):
        self._paths: List[str] = []
        self._highlight_sid: Optional[str] = None

    def clear(self) -> None:
        self._highlight_sid = None
        stage = omni.usd.get_context().get_stage()
        if not stage:
            self._paths.clear()
            return
        for p in list(self._paths):
            try:
                prim = stage.GetPrimAtPath(p)
                if prim and prim.IsValid():
                    stage.RemovePrim(p)
            except Exception:
                pass
        self._paths.clear()

    def _latlon_to_usd(self, lat: float, lon: float, height_m: float = 0.0) -> Optional[Tuple[float, float, float]]:
        try:
            from younite.usd_viewer_stage_core_extension import get_geo_coordinate_service

            geo = get_geo_coordinate_service()
            if geo and geo.ready:
                return geo.latlon_to_usd(float(lat), float(lon), float(height_m))
        except Exception:
            pass
        return None

    def _world_xyz_for_marker(
        self, geo, lat: float, lon: float
    ) -> Optional[Tuple[float, float, float]]:
        """
        Horizontal position from WGS84; vertical aligned like transit_overlay — raw ellipsoid
        heights bury short poles under Cesium tiles, while air-quality poles are tall enough
        to remain visible without snap.
        """
        try:
            from younite.usd_viewer_stage_core_extension.services.core_services.geo_teleport_transform import (
                snap_geo_scene_position_to_ground,
            )

            oh = float(geo.origin[2])
            raw = geo.latlon_to_usd(float(lat), float(lon), oh + 4.0)
            if not raw:
                return None
            x, y, z = float(raw[0]), float(raw[1]), float(raw[2])
            x, y, z = snap_geo_scene_position_to_ground(x, y, z, quiet=True)
            return (x, y, z)
        except Exception:
            return None

    def sync_stations(self, stations: List[Dict[str, Any]]) -> int:
        """
        Replace markers. Each item: { id, lat, lon, name?, category?, opening_hours?, detail? }.
        """
        self.clear()
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return 0

        parent = stage.GetPrimAtPath(STATIONS_ROOT)
        if not parent or not parent.IsValid():
            if not _ensure_stations_root(stage):
                return 0
            parent = stage.GetPrimAtPath(STATIONS_ROOT)
            if not parent or not parent.IsValid():
                return 0

        from younite.usd_viewer_stage_core_extension import get_geo_coordinate_service

        geo = get_geo_coordinate_service()
        if not geo or not geo.ready:
            return 0

        count = 0
        used = set()
        for idx, item in enumerate(stations):
            lat = item.get("lat")
            lon = item.get("lon")
            if lat is None or lon is None:
                continue
            sid = _sanitize_id(item.get("id", idx))
            while sid in used:
                sid = f"{sid}_{idx}"
            used.add(sid)
            path = f"{STATIONS_ROOT}/{sid}"
            coords = self._world_xyz_for_marker(geo, float(lat), float(lon))
            if not coords:
                continue
            x, y, z = coords
            cat = str(item.get("category") or "").strip() or "unknown"
            name = str(item.get("name") or sid)[:200]
            detail = str(item.get("detail") or "")[:400]
            oh = item.get("opening_hours")
            oh_s = str(oh)[:200] if oh else ""

            existing = stage.GetPrimAtPath(path)
            if existing and existing.IsValid():
                try:
                    stage.RemovePrim(path)
                except Exception:
                    pass

            root = UsdGeom.Xform.Define(stage, path)
            if not root:
                continue
            xf = UsdGeom.Xformable(root)
            xf.ClearXformOpOrder()
            xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(x, y, z))

            prim = stage.GetPrimAtPath(path)
            if prim:
                prim.SetCustomDataByKey("iot:lat", float(lat))
                prim.SetCustomDataByKey("iot:lon", float(lon))
                prim.SetCustomDataByKey("iot:name", name)
                prim.SetCustomDataByKey("iot:category", cat)
                if detail:
                    prim.SetCustomDataByKey("iot:detail", detail)
                if oh_s:
                    prim.SetCustomDataByKey("iot:opening_hours", oh_s)

            pn = _POLE_AND_BEACON_RGB
            pole_path = f"{path}/Pole"
            cyl = UsdGeom.Cylinder.Define(stage, pole_path)
            if cyl:
                cyl.GetHeightAttr().Set(_OSM_POLE_HEIGHT_CM)
                cyl.GetRadiusAttr().Set(_OSM_POLE_RADIUS_CM)
                pxf = UsdGeom.Xformable(cyl)
                pxf.ClearXformOpOrder()
                pxf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                    Gf.Vec3d(0.0, _OSM_POLE_HEIGHT_CM * 0.5, 0.0)
                )
                pxf.AddRotateXOp(UsdGeom.XformOp.PrecisionDouble).Set(-90.0)
                pprim = stage.GetPrimAtPath(pole_path)
                pole_mat = f"{path}/MatPole"
                halo_mat = f"{path}/MatHalo"
                _make_preview_emissive_material(
                    stage, pole_mat, pn, emissive_scale=2.8, opacity=1.0
                )
                _make_preview_emissive_material(
                    stage,
                    halo_mat,
                    _UNSEL_HALO_RGB,
                    emissive_scale=_OSM_HALO_EMISSIVE,
                    opacity=_OSM_HALO_OPACITY,
                )
                if pprim and pprim.IsValid():
                    _bind_material(stage, pole_path, pole_mat)
                show_hide(pole_path, True, priority=Priority.CRITICAL, source=SOURCE)

            halo_path = f"{path}/Halo"
            halo_r = _OSM_HALO_RADIUS_CM
            sph = UsdGeom.Sphere.Define(stage, halo_path)
            if sph:
                sph.GetRadiusAttr().Set(halo_r)
                sxf = UsdGeom.Xformable(sph)
                sxf.ClearXformOpOrder()
                crown_y = _OSM_POLE_HEIGHT_CM + halo_r
                sxf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.0, crown_y, 0.0))
                hprim = stage.GetPrimAtPath(halo_path)
                if hprim and hprim.IsValid():
                    _bind_material(stage, halo_path, halo_mat)
                show_hide(halo_path, True, priority=Priority.CRITICAL, source=SOURCE)

            beacon_path = f"{path}/Beacon"
            bsp = UsdGeom.Sphere.Define(stage, beacon_path)
            if bsp:
                bsp.GetRadiusAttr().Set(_OSM_BEACON_RADIUS_CM)
                bxf = UsdGeom.Xformable(bsp)
                bxf.ClearXformOpOrder()
                by = _OSM_BEACON_RADIUS_CM + _ANCHOR_BEACON_LIFT_CM
                bxf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.0, by, 0.0))
                b_mat = f"{path}/MatBeacon"
                _make_preview_emissive_material(
                    stage,
                    b_mat,
                    _UNSEL_BEACON_RGB,
                    emissive_scale=_OSM_BEACON_EMISSIVE,
                    opacity=0.92,
                )
                if stage.GetPrimAtPath(beacon_path) and stage.GetPrimAtPath(beacon_path).IsValid():
                    _bind_material(stage, beacon_path, b_mat)
                show_hide(beacon_path, True, priority=Priority.CRITICAL, source=SOURCE)

            self._paths.append(path)
            count += 1

        # Highlight may arrive before this sync on WebRTC; re-apply so new prims pick up selection.
        self._apply_highlight()
        return count

    def set_highlight_station_id(self, station_id: Optional[str]) -> None:
        sid = str(station_id).strip() if station_id is not None else ""
        self._highlight_sid = sid if sid else None
        self._apply_highlight()

    def _apply_highlight(self) -> None:
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            hi = self._highlight_sid
            pn = _POLE_AND_BEACON_RGB
            for path in self._paths:
                sid = _path_to_station_id(path)
                base_r = float(_OSM_HALO_RADIUS_CM)
                selected = bool(hi) and sid == hi

                if selected:
                    hr = base_r * 1.58
                elif hi:
                    hr = base_r * 0.78
                else:
                    hr = base_r

                halo_path = f"{path}/Halo"
                hprim = stage.GetPrimAtPath(halo_path)
                if hprim and hprim.IsValid():
                    try:
                        halo_sphere = UsdGeom.Sphere(hprim)
                        if halo_sphere:
                            halo_sphere.GetRadiusAttr().Set(float(hr))
                        hx = UsdGeom.Xformable(hprim)
                        hx.ClearXformOpOrder()
                        hx.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                            Gf.Vec3d(0.0, float(_OSM_POLE_HEIGHT_CM) + float(hr), 0.0)
                        )
                    except Exception:
                        pass
                if selected:
                    pole_em, halo_em, beacon_em = 3.0, 4.2, 3.6
                elif hi:
                    pole_em, halo_em, beacon_em = 1.35, 1.15, 1.85
                else:
                    pole_em, halo_em, beacon_em = 2.8, 2.45, _OSM_BEACON_EMISSIVE
                if selected:
                    _set_preview_mat_colors(stage, f"{path}/MatPole", pn, pole_em)
                    _set_preview_mat_colors(
                        stage,
                        f"{path}/MatHalo",
                        _SELECT_HALO_RGB,
                        halo_em,
                    )
                    _set_preview_mat_colors(
                        stage,
                        f"{path}/MatBeacon",
                        _SELECT_BEACON_RGB,
                        beacon_em,
                    )
                else:
                    _set_preview_mat_colors(stage, f"{path}/MatPole", pn, pole_em)
                    if hi:
                        h_rgb, b_rgb = _UNSEL_HALO_DIM_RGB, _UNSEL_BEACON_DIM_RGB
                    else:
                        h_rgb, b_rgb = _UNSEL_HALO_RGB, _UNSEL_BEACON_RGB
                    _set_preview_mat_colors(stage, f"{path}/MatHalo", h_rgb, halo_em)
                    _set_preview_mat_colors(stage, f"{path}/MatBeacon", b_rgb, beacon_em)
        except Exception:
            pass

    def set_group_visible(self, visible: bool) -> None:
        items = []
        for p in self._paths:
            for suffix in ("/Pole", "/Halo", "/Beacon"):
                items.append((p + suffix, visible))
        if not items and visible:
            return
        if items:
            batch_show_hide(
                items, priority=Priority.CRITICAL, source=SOURCE, group="iot_osm_pois_visible"
            )
