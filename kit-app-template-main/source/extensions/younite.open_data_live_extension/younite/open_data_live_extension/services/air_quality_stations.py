"""
Runtime air-quality station markers under /World/IoT_AirQuality/Stations.

Part of ``younite.open_data_live_extension``. Data source on the web side: WAQI (see dev IotSubmenu).
Coordinates: WGS84 -> USD via GeoCoordinateService.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import omni.usd
from pxr import Gf, UsdGeom

from younite.payload_orchestrator_core_extension import batch_show_hide, show_hide

STATIONS_ROOT = "/World/IoT_AirQuality/Stations"
_IOT_MAT_ROOT = "/World/IoT_AirQuality/_IoTPreviewMaterials"
SOURCE = "open_data_live"

# Scene units are cm (metersPerUnit 0.01). Pole + crown sphere read from bird-eye without dominating the view.
_POLE_HEIGHT_CM = 10_000.0  # 100 m
_POLE_RADIUS_CM = 450.0  # 4.5 m radius (~9 m cylinder)
_BEACON_RADIUS_CM = 260.0
_ANCHOR_BEACON_LIFT_CM = 140.0  # keeps ground pin slightly above anchor (z-fight / terrain mismatch)
# Poles + ground pin share one neutral look; only the crown sphere uses AQI palette.
_POLE_AND_BEACON_RGB: Tuple[float, float, float] = (0.38, 0.48, 0.56)


def _sanitize_id(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", str(raw or "station"))
    if s and s[0].isdigit():
        s = "s_" + s
    return s or "station"


def _aqi_color(aqi: float) -> Tuple[float, float, float]:
    try:
        v = float(aqi)
    except Exception:
        return (0.5, 0.5, 0.5)
    if v < 0:
        v = 0
    if v <= 50:
        return (0.2, 0.85, 0.3)
    # 51–100 = Moderate on US AQI — yellow (not lime: R > G reads clearly yellow on stream)
    if v <= 100:
        return (0.98, 0.82, 0.12)
    if v <= 150:
        return (0.95, 0.55, 0.15)
    if v <= 200:
        return (0.95, 0.35, 0.15)
    return (0.9, 0.15, 0.15)


def _halo_radius_cm(aqi: float) -> float:
    """Sphere radius (cm) for the **crown** marker on the pole top — UX only, not sensor range."""
    try:
        v = float(aqi)
    except Exception:
        v = -1.0
    if v < 0:
        v = 40.0
    v = max(0.0, min(500.0, v))
    # ~18 m … ~55 m — large emissive bubble above the pole, readable from overview
    return 1800.0 + (v / 500.0) * 3700.0


def _path_to_station_id(station_path: str) -> str:
    """Last path segment = sanitized station id (matches web `id` after `_sanitize_id`)."""
    parts = str(station_path or "").rstrip("/").split("/")
    return parts[-1] if parts else ""


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _ensure_iot_material_root(stage) -> None:
    p = stage.GetPrimAtPath(_IOT_MAT_ROOT)
    if p and p.IsValid():
        return
    try:
        UsdGeom.Xform.Define(stage, _IOT_MAT_ROOT)
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
    """UsdPreviewSurface + emissive so markers show under RTX (displayColor alone is often invisible)."""
    try:
        from pxr import Sdf, UsdShade

        prim = stage.GetPrimAtPath(mat_path)
        if prim and prim.IsValid():
            return
        _ensure_iot_material_root(stage)
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
        dc = sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)
        dc.Set(diff)
        ec = sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f)
        ec.Set(em)
    except Exception:
        pass


class AirQualityStationsService:
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
        Replace all station prims with the given list.

        Each item: { id, lat, lon, aqi?, pm25?, tempC?, name?, time? } (aqi used for color + halo).
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
                aqi = float(item.get("aqi", -1) or -1)
            except Exception:
                aqi = -1.0
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
                prim.SetCustomDataByKey("iot:aqi", float(aqi))
                prim.SetCustomDataByKey("iot:name", name)
                if item.get("pm25") is not None:
                    try:
                        prim.SetCustomDataByKey("iot:pm25", float(item["pm25"]))
                    except Exception:
                        pass
                if item.get("tempC") is not None:
                    try:
                        prim.SetCustomDataByKey("iot:temp_c", float(item["tempC"]))
                    except Exception:
                        pass
                if item.get("time") is not None:
                    prim.SetCustomDataByKey("iot:time", str(item["time"]))

            sphere_col = _aqi_color(aqi)
            pn = _POLE_AND_BEACON_RGB
            # Vertical cylinder (constant width — reads from bird's-eye; cone was too thin).
            pole_path = f"{path}/Pole"
            cyl = UsdGeom.Cylinder.Define(stage, pole_path)
            if cyl:
                cyl.GetHeightAttr().Set(_POLE_HEIGHT_CM)
                cyl.GetRadiusAttr().Set(_POLE_RADIUS_CM)
                pxf = UsdGeom.Xformable(cyl)
                pxf.ClearXformOpOrder()
                # UsdGeom.Cylinder default spine is **Z**. xformOpOrder applies **last op first** to
                # points; we need world = Translate * Rotate * local so base sits on the station root.
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

            # Large tinted sphere **above the pole** (center = pole top + R so it sits on the cap).
            halo_path = f"{path}/Halo"
            halo_r = _halo_radius_cm(aqi)
            sph = UsdGeom.Sphere.Define(stage, halo_path)
            if sph:
                sph.GetRadiusAttr().Set(halo_r)
                sxf = UsdGeom.Xformable(sph)
                sxf.ClearXformOpOrder()
                crown_y = _POLE_HEIGHT_CM + halo_r
                sxf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.0, crown_y, 0.0))
                hprim = stage.GetPrimAtPath(halo_path)
                halo_mat = f"{path}/MatHalo"
                if hprim and hprim.IsValid():
                    _bind_material(stage, halo_path, halo_mat)
                show_hide(halo_path, True, source=SOURCE)

            # Small ground pin at the anchor.
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

            # Do not set visibility on the root Xform: inherited visibility would hide Cone/Sphere.
            self._paths.append(path)
            count += 1

        return count

    def set_highlight_station_id(self, station_id: Optional[str]) -> None:
        """Brighter neutral pole/beacon + larger AQI sphere for selection; ``None`` clears emphasis."""
        sid = str(station_id).strip() if station_id is not None else ""
        self._highlight_sid = sid if sid else None
        self._apply_highlight()

    def _read_root_aqi(self, root_path: str) -> float:
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return -1.0
            prim = stage.GetPrimAtPath(str(root_path))
            if not prim or not prim.IsValid():
                return -1.0
            v = prim.GetCustomDataByKey("iot:aqi")
            return float(v) if v is not None else -1.0
        except Exception:
            return -1.0

    def _apply_highlight(self) -> None:
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            hi = self._highlight_sid
            pn = _POLE_AND_BEACON_RGB
            for path in self._paths:
                sid = _path_to_station_id(path)
                aqi = self._read_root_aqi(path)
                base = _aqi_color(aqi)
                base_r = float(_halo_radius_cm(aqi))
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
            # No geometry yet
            return
        if items:
            batch_show_hide(items, source=SOURCE, group="iot_air_visible")
