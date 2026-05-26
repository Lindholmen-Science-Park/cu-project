"""
Runtime bike-share dock markers under /World/IoT_BikeShare/Stations.

Data source on the web side: GBFS (Styr & Ställ / nextbike_zg). Coordinates: WGS84 -> USD via GeoCoordinateService.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import omni.usd
from pxr import Gf, UsdGeom

from younite.payload_orchestrator_core_extension import batch_show_hide, show_hide

from .air_quality_stations import (
    _ANCHOR_BEACON_LIFT_CM,
    _BEACON_RADIUS_CM,
    _POLE_AND_BEACON_RGB,
    _POLE_HEIGHT_CM,
    _POLE_RADIUS_CM,
    _clamp01,
    _sanitize_id,
)

STATIONS_ROOT = "/World/IoT_BikeShare/Stations"
_BIKE_MAT_ROOT = "/World/IoT_BikeShare/_PreviewMaterials"
SOURCE = "open_data_live"


def _path_to_station_id(station_path: str) -> str:
    parts = str(station_path or "").rstrip("/").split("/")
    return parts[-1] if parts else ""


def _bike_halo_radius_cm(bikes: int) -> float:
    try:
        b = int(bikes)
    except Exception:
        b = 0
    b = max(0, min(80, b))
    return 1800.0 + float(b) * 95.0


def _bike_crown_color(bikes: int, docks: int) -> Tuple[float, float, float]:
    """Dock halo: green when many bikes available, red when empty."""
    try:
        bi = int(bikes)
    except Exception:
        bi = 0
    try:
        dk = int(docks)
    except Exception:
        dk = 0
    if bi <= 0:
        return (0.92, 0.22, 0.2)
    cap = max(1, bi + dk)
    ratio = bi / float(cap)
    if ratio >= 0.35 or bi >= 5:
        return (0.18, 0.82, 0.38)
    if bi >= 2:
        return (0.98, 0.78, 0.15)
    return (0.95, 0.52, 0.18)


def _ensure_bike_material_root(stage) -> None:
    p = stage.GetPrimAtPath(_BIKE_MAT_ROOT)
    if p and p.IsValid():
        return
    try:
        UsdGeom.Xform.Define(stage, _BIKE_MAT_ROOT)
    except Exception:
        pass


def _make_preview_emissive_material(
    stage,
    mat_path: str,
    rgb: Tuple[float, float, float],
    *,
    emissive_scale: float,
    opacity: float,
) -> None:
    try:
        from pxr import Sdf, UsdShade

        prim = stage.GetPrimAtPath(mat_path)
        if prim and prim.IsValid():
            return
        _ensure_bike_material_root(stage)
        mat = UsdShade.Material.Define(stage, mat_path)
        sh_path = f"{mat_path}/PreviewSurface"
        sh = UsdShade.Shader.Define(stage, sh_path)
        sh.CreateIdAttr("UsdPreviewSurface")
        r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
        diff = Gf.Vec3f(_clamp01(r), _clamp01(g), _clamp01(b))
        es = float(emissive_scale)
        em = Gf.Vec3f(
            min(14.0, max(0.0, r * es)),
            min(14.0, max(0.0, g * es)),
            min(14.0, max(0.0, b * es)),
        )
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(diff)
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(em)
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.42)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opacity))
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    except Exception:
        pass


def _bind_material(stage, geom_prim_path: str, mat_path: str) -> None:
    try:
        from pxr import UsdShade

        gprim = stage.GetPrimAtPath(str(geom_prim_path))
        mprim = stage.GetPrimAtPath(str(mat_path))
        if not (gprim and gprim.IsValid() and mprim and mprim.IsValid()):
            return
        mat = UsdShade.Material(mprim)
        if not mat:
            return
        UsdShade.MaterialBindingAPI.Apply(gprim).Bind(mat)
    except Exception:
        pass


def _set_preview_mat_colors(stage, mat_path: str, rgb: Tuple[float, float, float], emissive_scale: float) -> None:
    try:
        from pxr import Sdf, UsdShade

        sh_path = f"{mat_path}/PreviewSurface"
        shp = stage.GetPrimAtPath(sh_path)
        if not shp or not shp.IsValid():
            return
        sh = UsdShade.Shader(shp)
        if not sh:
            return
        r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
        diff = Gf.Vec3f(_clamp01(r), _clamp01(g), _clamp01(b))
        es = float(emissive_scale)
        em = Gf.Vec3f(
            min(14.0, max(0.0, r * es)),
            min(14.0, max(0.0, g * es)),
            min(14.0, max(0.0, b * es)),
        )
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(diff)
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(em)
    except Exception:
        pass


class BikeShareStationsService:
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

    def sync_stations(self, stations: List[Dict[str, Any]]) -> int:
        """
        Replace all dock markers with the given list.

        Each item: { id, lat, lon, name?, bikesAvailable?, docksAvailable? }.
        """
        self.clear()
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return 0

        parent = stage.GetPrimAtPath(STATIONS_ROOT)
        if not parent or not parent.IsValid():
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
            coords = self._latlon_to_usd(float(lat), float(lon), 0.0)
            if not coords:
                continue
            x, y, z = coords
            try:
                bikes = int(item.get("bikesAvailable", 0) or 0)
            except Exception:
                bikes = 0
            try:
                docks = int(item.get("docksAvailable", 0) or 0)
            except Exception:
                docks = 0
            name = str(item.get("name") or sid)[:200]

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
                prim.SetCustomDataByKey("iot:bikes", int(bikes))
                prim.SetCustomDataByKey("iot:docks", int(docks))

            sphere_col = _bike_crown_color(bikes, docks)
            pn = _POLE_AND_BEACON_RGB
            pole_path = f"{path}/Pole"
            cyl = UsdGeom.Cylinder.Define(stage, pole_path)
            if cyl:
                cyl.GetHeightAttr().Set(_POLE_HEIGHT_CM)
                cyl.GetRadiusAttr().Set(_POLE_RADIUS_CM)
                pxf = UsdGeom.Xformable(cyl)
                pxf.ClearXformOpOrder()
                pxf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                    Gf.Vec3d(0.0, _POLE_HEIGHT_CM * 0.5, 0.0)
                )
                pxf.AddRotateXOp(UsdGeom.XformOp.PrecisionDouble).Set(-90.0)
                pprim = stage.GetPrimAtPath(pole_path)
                pole_mat = f"{path}/MatPole"
                halo_mat = f"{path}/MatHalo"
                _make_preview_emissive_material(
                    stage, pole_mat, pn, emissive_scale=2.8, opacity=1.0
                )
                _make_preview_emissive_material(
                    stage, halo_mat, sphere_col, emissive_scale=2.0, opacity=0.48
                )
                if pprim and pprim.IsValid():
                    _bind_material(stage, pole_path, pole_mat)
                show_hide(pole_path, True, source=SOURCE)

            halo_path = f"{path}/Halo"
            halo_r = _bike_halo_radius_cm(bikes)
            sph = UsdGeom.Sphere.Define(stage, halo_path)
            if sph:
                sph.GetRadiusAttr().Set(halo_r)
                sxf = UsdGeom.Xformable(sph)
                sxf.ClearXformOpOrder()
                crown_y = _POLE_HEIGHT_CM + halo_r
                sxf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.0, crown_y, 0.0))
                hprim = stage.GetPrimAtPath(halo_path)
                if hprim and hprim.IsValid():
                    _bind_material(stage, halo_path, halo_mat)
                show_hide(halo_path, True, source=SOURCE)

            beacon_path = f"{path}/Beacon"
            bsp = UsdGeom.Sphere.Define(stage, beacon_path)
            if bsp:
                bsp.GetRadiusAttr().Set(_BEACON_RADIUS_CM)
                bxf = UsdGeom.Xformable(bsp)
                bxf.ClearXformOpOrder()
                by = _BEACON_RADIUS_CM + _ANCHOR_BEACON_LIFT_CM
                bxf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.0, by, 0.0))
                b_mat = f"{path}/MatBeacon"
                _make_preview_emissive_material(
                    stage, b_mat, pn, emissive_scale=4.2, opacity=0.92
                )
                if stage.GetPrimAtPath(beacon_path) and stage.GetPrimAtPath(beacon_path).IsValid():
                    _bind_material(stage, beacon_path, b_mat)
                show_hide(beacon_path, True, source=SOURCE)

            self._paths.append(path)
            count += 1

        return count

    def set_highlight_station_id(self, station_id: Optional[str]) -> None:
        sid = str(station_id).strip() if station_id is not None else ""
        self._highlight_sid = sid if sid else None
        self._apply_highlight()

    def _read_root_bikes_docks(self, root_path: str) -> Tuple[int, int]:
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return 0, 0
            prim = stage.GetPrimAtPath(str(root_path))
            if not prim or not prim.IsValid():
                return 0, 0
            b = prim.GetCustomDataByKey("iot:bikes")
            d = prim.GetCustomDataByKey("iot:docks")
            return int(b) if b is not None else 0, int(d) if d is not None else 0
        except Exception:
            return 0, 0

    def _apply_highlight(self) -> None:
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            hi = self._highlight_sid
            pn = _POLE_AND_BEACON_RGB
            for path in self._paths:
                sid = _path_to_station_id(path)
                bikes, docks = self._read_root_bikes_docks(path)
                base = _bike_crown_color(bikes, docks)
                base_r = float(_bike_halo_radius_cm(bikes))
                selected = bool(hi) and sid == hi

                if selected:
                    pr = _clamp01(base[0] * 1.22 + 0.08)
                    pg = _clamp01(base[1] * 1.18 + 0.06)
                    pb = _clamp01(base[2] * 1.12 + 0.04)
                    hr = base_r * 1.48
                elif hi:
                    pr = base[0] * 0.38 + 0.12
                    pg = base[1] * 0.38 + 0.12
                    pb = base[2] * 0.38 + 0.12
                    hr = base_r * 0.78
                else:
                    pr, pg, pb = base[0], base[1], base[2]
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
                            Gf.Vec3d(0.0, float(_POLE_HEIGHT_CM) + float(hr), 0.0)
                        )
                    except Exception:
                        pass
                if selected:
                    pole_em, halo_em, beacon_em = 4.4, 3.0, 6.5
                elif hi:
                    pole_em, halo_em, beacon_em = 1.35, 0.95, 1.9
                else:
                    pole_em, halo_em, beacon_em = 2.8, 2.0, 4.2
                _set_preview_mat_colors(stage, f"{path}/MatPole", pn, pole_em)
                dim_h = 0.88 if selected else (0.38 if hi else 0.6)
                _set_preview_mat_colors(
                    stage,
                    f"{path}/MatHalo",
                    (_clamp01(pr * dim_h), _clamp01(pg * dim_h), _clamp01(pb * dim_h)),
                    halo_em,
                )
                _set_preview_mat_colors(stage, f"{path}/MatBeacon", pn, beacon_em)
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
            batch_show_hide(items, source=SOURCE, group="iot_bike_visible")
