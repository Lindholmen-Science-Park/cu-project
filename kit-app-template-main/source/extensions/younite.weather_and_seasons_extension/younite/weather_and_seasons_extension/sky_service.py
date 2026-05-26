"""
Sky control: applies time-of-day, clouds, and sun direction to the dynamic sky.
Enforces minimum light intensities so the scene is never pitch black (references may load with 0 or low values).
"""

# Weather presets: cloud_coverage (-0.5 blue sky to 0.5 overcast),
# sun/dome intensity, sun color (RGB — warm white for clear, cool blue-gray for storms)
WEATHER_PRESETS = {
    "clearSky":      {"cloud_coverage": -0.5, "cumulus": True,  "distant": 5000, "dome": 0.9,  "sun_color": (1.0, 0.98, 0.95), "rain": 0.0, "snow": 0.0},
    "partlyCloudy":  {"cloud_coverage":  0.0, "cumulus": True,  "distant": 4500, "dome": 0.85, "sun_color": (0.95, 0.95, 0.95), "rain": 0.0, "snow": 0.0},
    "cloudy":        {"cloud_coverage":  0.3, "cumulus": True,  "distant": 3500, "dome": 0.7,  "sun_color": (0.85, 0.87, 0.92), "rain": 0.0, "snow": 0.0},
    "overcast":      {"cloud_coverage":  0.5, "cumulus": True,  "distant": 2500, "dome": 0.55, "sun_color": (0.75, 0.78, 0.85), "rain": 0.0, "snow": 0.0},
    "foggy":         {"cloud_coverage":  0.5, "cumulus": True,  "distant": 1500, "dome": 0.35, "sun_color": (0.6, 0.63, 0.72),  "rain": 0.0, "snow": 0.0, "fog": 0.5},
    "rainy":         {"cloud_coverage":  0.5, "cumulus": True,  "distant": 1500, "dome": 0.35, "sun_color": (0.6, 0.63, 0.72),  "rain": 0.5, "snow": 0.0},
    "snowy":         {"cloud_coverage":  0.5, "cumulus": True,  "distant": 1500, "dome": 0.35, "sun_color": (0.6, 0.63, 0.72),  "rain": 0.0, "snow": 0.5},
    "darkStorm":     {"cloud_coverage":  0.5, "cumulus": True,  "distant":  800, "dome": 0.2,  "sun_color": (0.45, 0.48, 0.58), "rain": 1.0, "snow": 0.0},
    "lightSnow":     {"cloud_coverage":  0.35, "cumulus": True, "distant": 3500, "dome": 0.65, "sun_color": (0.88, 0.9, 0.95),   "rain": 0.0, "snow": 0.5},
    "heavySnow":     {"cloud_coverage":  0.5, "cumulus": True,  "distant": 2200, "dome": 0.45, "sun_color": (0.72, 0.76, 0.88),  "rain": 0.0, "snow": 1.0},
}


_desired_rain: float = 0.0
_desired_snow: float = 0.0


def get_desired_precipitation() -> tuple[float, float]:
    """Return (rain_intensity, snow_intensity) regardless of current view type."""
    return (_desired_rain, _desired_snow)


def _is_bird_eye() -> bool:
    try:
        import carb
        return carb.settings.get_settings().get("/younite/camera/viewType") == "birdEye"
    except Exception:
        return False


def apply_sky_control(raw_payload):
    """Apply sky/environment controls to the current USD stage.

    Sets Environment-prim properties, shader inputs, AND axis rotations
    (AxisSHA, AxisDeclination, AxisAzimuth, AxisElevation) to position the
    DistantLight consistently with the DomeLight sky texture.

    Returns:
        "ok" if environment and DistantLight were found and time-of-day applied.
        "no_env" if /World/Environment was missing.
        "no_light" if Environment existed but DistantLight was not found.
    """
    try:
        import omni.usd
        from pxr import UsdGeom, Usd

        from younite.messaging_core_extension.message_utils import normalize_event_payload

        payload = normalize_event_payload(raw_payload)

        if not isinstance(payload, dict):
            return "ok"

        stage = omni.usd.get_context().get_stage()
        if not stage:
            print("[sky] No USD stage available for sky control")
            return "no_env"

        env_prim = stage.GetPrimAtPath("/World/Environment")

        if not env_prim or not env_prim.IsValid():
            print("[sky] /World/Environment not found or invalid — sky control skipped (stage may still be loading)")
            return "no_env"

        env_base = str(env_prim.GetPath())
        sky_shader_prim = stage.GetPrimAtPath(f"{env_base}/sky/Looks/SkyMaterial/Shader")
        if not sky_shader_prim or not sky_shader_prim.IsValid():
            sky_shader_prim = None

        axis_sha_prim = stage.GetPrimAtPath(f"{env_base}/sky/AxisNorth/AxisLatitude/AxisSHA")
        axis_declination_prim = stage.GetPrimAtPath(f"{env_base}/sky/AxisNorth/AxisLatitude/AxisSHA/AxisDeclination")
        axis_azimuth_prim = stage.GetPrimAtPath(f"{env_base}/sky/AxisNorth/AxisAzimuth")
        axis_elevation_prim = stage.GetPrimAtPath(f"{env_base}/sky/AxisNorth/AxisAzimuth/AxisElevation")
        if not axis_sha_prim or not axis_sha_prim.IsValid():
            axis_sha_prim = None
        if not axis_declination_prim or not axis_declination_prim.IsValid():
            axis_declination_prim = None
        if not axis_azimuth_prim or not axis_azimuth_prim.IsValid():
            axis_azimuth_prim = None
        if not axis_elevation_prim or not axis_elevation_prim.IsValid():
            axis_elevation_prim = None

        distant_light_prim = stage.GetPrimAtPath(f"{env_base}/sky/AxisNorth/AxisLatitude/AxisSHA/AxisDeclination/DistantLight")
        if not distant_light_prim or not distant_light_prim.IsValid():
            distant_light_prim = None

        dome_light_prim = stage.GetPrimAtPath(f"{env_base}/sky/DomeLight")
        if not dome_light_prim or not dome_light_prim.IsValid():
            dome_light_prim = None

        edit_context = Usd.EditContext(stage, Usd.EditTarget(stage.GetSessionLayer()))

        with edit_context:
            import math
            from pxr import Sdf, Gf

            def set_attribute(prim, attr_name, value, attr_type=float):
                if not prim:
                    return False
                attr = prim.GetAttribute(attr_name)
                if not attr:
                    if attr_type == float:
                        attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Float)
                    elif attr_type == bool:
                        attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Bool)
                    elif attr_type == int:
                        attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Int)
                    else:
                        return False
                if not attr:
                    return False
                try:
                    if attr_type == bool:
                        converted_value = bool(value)
                    elif attr_type == int:
                        converted_value = int(value)
                    else:
                        converted_value = float(value)
                    return attr.Set(converted_value)
                except Exception as e:
                    print(f"[sky] Error setting {attr_name}: {e}")
                    return False

            def calculate_solar_angles(time_of_day, day_of_year, latitude=51.426):
                sha_degrees = 15.0 * (time_of_day - 12.0)
                declination_rad = math.radians(360.0 * (284.0 + day_of_year) / 365.0)
                declination_degrees = 23.45 * math.sin(declination_rad)

                lat_rad = math.radians(latitude)
                sha_rad = math.radians(sha_degrees)
                dec_rad = math.radians(declination_degrees)

                elevation_rad = math.asin(
                    math.sin(lat_rad) * math.sin(dec_rad)
                    + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(sha_rad)
                )
                elevation_degrees = math.degrees(elevation_rad)

                if elevation_degrees > 0:
                    az_cos = (math.sin(dec_rad) - math.sin(elevation_rad) * math.sin(lat_rad)) / (
                        math.cos(elevation_rad) * math.cos(lat_rad)
                    )
                    az_cos = max(-1.0, min(1.0, az_cos))
                    azimuth_rad = math.acos(az_cos)
                    if sha_degrees > 0:
                        azimuth_degrees = 180.0 - math.degrees(azimuth_rad)
                    else:
                        azimuth_degrees = 180.0 + math.degrees(azimuth_rad)
                else:
                    azimuth_degrees = 180.0

                return {
                    "sha": sha_degrees,
                    "declination": declination_degrees,
                    "elevation": elevation_degrees,
                    "azimuth": azimuth_degrees,
                }

            current_time = payload.get("timeOfDay", None)
            current_day = payload.get("dayOfYear", None)
            current_lat = payload.get("latitude", None)

            def _to_float(val, default):
                if val is None:
                    return default
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return default

            latitude = 57.7089
            if current_lat is not None:
                latitude = _to_float(current_lat, latitude)
            elif sky_shader_prim:
                lat_attr = sky_shader_prim.GetAttribute("inputs:Latitude")
                if lat_attr:
                    latitude = lat_attr.Get() or latitude

            day_of_year = 187.0
            if current_day is not None:
                day_of_year = _to_float(current_day, day_of_year)
            elif sky_shader_prim:
                day_attr = sky_shader_prim.GetAttribute("inputs:DayOfYear")
                if day_attr:
                    day_of_year = day_attr.Get() or day_of_year

            time_of_day = 12.0
            if current_time is not None:
                time_of_day = _to_float(current_time, time_of_day)
            elif sky_shader_prim:
                time_attr = sky_shader_prim.GetAttribute("inputs:TimeOfDay")
                if time_attr:
                    time_of_day = time_attr.Get() or time_of_day

            recalculate_sun = (
                "timeOfDay" in payload or "dayOfYear" in payload or "latitude" in payload
            )
            solar_angles = None
            if recalculate_sun:
                solar_angles = calculate_solar_angles(time_of_day, day_of_year, latitude)

            def _set_axis_rotation(axis_prim, component, value):
                """Set one component (0=X, 1=Y, 2=Z in rotateZYX vec) on an axis prim."""
                if not axis_prim:
                    return
                rot_attr = axis_prim.GetAttribute("xformOp:rotateZYX")
                if rot_attr:
                    cur = rot_attr.Get()
                    vals = list(cur) if cur else [0.0, 0.0, 0.0]
                    vals[component] = value
                    rot_attr.Set(Gf.Vec3d(*vals))
                else:
                    xf = UsdGeom.Xformable(axis_prim)
                    op = xf.AddRotateZYXOp()
                    if op:
                        vals = [0.0, 0.0, 0.0]
                        vals[component] = value
                        op.Set(Gf.Vec3d(*vals))

            if "timeOfDay" in payload:
                time_of_day = _to_float(payload["timeOfDay"], time_of_day)
                if env_prim:
                    set_attribute(env_prim, "time:current", time_of_day, float)
                if sky_shader_prim:
                    set_attribute(sky_shader_prim, "inputs:TimeOfDay", time_of_day, float)
                    if recalculate_sun and solar_angles:
                        set_attribute(sky_shader_prim, "inputs:SHA", solar_angles["sha"], float)
                        set_attribute(sky_shader_prim, "inputs:Elevation", solar_angles["elevation"], float)
                        set_attribute(sky_shader_prim, "inputs:Azimuth", solar_angles["azimuth"], float)

                if recalculate_sun and solar_angles:
                    _set_axis_rotation(axis_sha_prim, 0, 180.0 - solar_angles["sha"])
                    _set_axis_rotation(axis_azimuth_prim, 1, solar_angles["azimuth"])
                    _set_axis_rotation(axis_elevation_prim, 2, solar_angles["elevation"])

            if "cloudCoverage" in payload:
                raw_coverage = _to_float(payload["cloudCoverage"], 0.5)
                cloud_coverage = raw_coverage - 0.5
                if env_prim:
                    set_attribute(env_prim, "weather:cloud_coverage", cloud_coverage, float)
                if sky_shader_prim:
                    set_attribute(sky_shader_prim, "inputs:CloudCoverage", cloud_coverage, float)

            if "dayOfYear" in payload:
                day_of_year = _to_float(payload["dayOfYear"], day_of_year)
                if sky_shader_prim:
                    set_attribute(sky_shader_prim, "inputs:DayOfYear", day_of_year, float)
                if recalculate_sun:
                    solar_angles = calculate_solar_angles(time_of_day, day_of_year, latitude)
                    _set_axis_rotation(axis_declination_prim, 2, solar_angles["declination"])
                    if sky_shader_prim:
                        set_attribute(sky_shader_prim, "inputs:Declination", solar_angles["declination"], float)
                        set_attribute(sky_shader_prim, "inputs:Elevation", solar_angles["elevation"], float)
                        set_attribute(sky_shader_prim, "inputs:Azimuth", solar_angles["azimuth"], float)

            if "latitude" in payload:
                latitude = _to_float(payload["latitude"], latitude)
                if env_prim:
                    set_attribute(env_prim, "location:latitude", latitude, float)
                if sky_shader_prim:
                    set_attribute(sky_shader_prim, "inputs:Latitude", latitude, float)
                solar_angles = calculate_solar_angles(time_of_day, day_of_year, latitude)
                _set_axis_rotation(axis_sha_prim, 0, 180.0 - solar_angles["sha"])
                _set_axis_rotation(axis_declination_prim, 2, solar_angles["declination"])
                _set_axis_rotation(axis_azimuth_prim, 1, solar_angles["azimuth"])
                _set_axis_rotation(axis_elevation_prim, 2, solar_angles["elevation"])
                if sky_shader_prim:
                    set_attribute(sky_shader_prim, "inputs:SHA", solar_angles["sha"], float)
                    set_attribute(sky_shader_prim, "inputs:Declination", solar_angles["declination"], float)
                    set_attribute(sky_shader_prim, "inputs:Elevation", solar_angles["elevation"], float)
                    set_attribute(sky_shader_prim, "inputs:Azimuth", solar_angles["azimuth"], float)

            if "longitude" in payload:
                longitude = _to_float(payload["longitude"], 11.97)
                if env_prim:
                    set_attribute(env_prim, "location:longitude", longitude, float)
                if sky_shader_prim:
                    set_attribute(sky_shader_prim, "inputs:Longitude", longitude, float)

            if "cumulusEnabled" in payload:
                cumulus_enabled = bool(payload["cumulusEnabled"])
                if env_prim:
                    set_attribute(env_prim, "weather:cumulus_enabled", cumulus_enabled, bool)
                if sky_shader_prim:
                    set_attribute(sky_shader_prim, "inputs:CumulusEnabled", cumulus_enabled, bool)

            if "weatherPreset" in payload:
                preset_key = str(payload["weatherPreset"])
                preset = WEATHER_PRESETS.get(preset_key)
                if preset:
                    cc = preset["cloud_coverage"]
                    cu = preset["cumulus"]
                    if env_prim:
                        set_attribute(env_prim, "weather:cloud_coverage", cc, float)
                        set_attribute(env_prim, "weather:cumulus_enabled", cu, bool)
                    if sky_shader_prim:
                        set_attribute(sky_shader_prim, "inputs:CloudCoverage", cc, float)
                        set_attribute(sky_shader_prim, "inputs:CumulusEnabled", cu, bool)
                    if distant_light_prim:
                        set_attribute(distant_light_prim, "inputs:intensity", preset["distant"], float)
                        sc = preset.get("sun_color", (1.0, 0.98, 0.95))
                        color_attr = distant_light_prim.GetAttribute("inputs:color")
                        if color_attr:
                            color_attr.Set(Gf.Vec3f(sc[0], sc[1], sc[2]))
                        else:
                            distant_light_prim.CreateAttribute("inputs:color", Sdf.ValueTypeNames.Color3f).Set(
                                Gf.Vec3f(sc[0], sc[1], sc[2])
                            )
                    if dome_light_prim:
                        set_attribute(dome_light_prim, "inputs:intensity", preset["dome"], float)
                    try:
                        global _desired_rain, _desired_snow
                        from .rain_service import start_rain, stop_rain
                        from .snow_service import start_snow, stop_snow
                        from .wet_ground_service import set_wet
                        rain_intensity = float(preset.get("rain", 0.0))
                        snow_intensity = float(preset.get("snow", 0.0))
                        _desired_rain = rain_intensity
                        _desired_snow = snow_intensity
                        precipitation = rain_intensity > 0 or snow_intensity > 0
                        bird_eye = _is_bird_eye()
                        if snow_intensity > 0:
                            stop_rain()
                            if not bird_eye:
                                start_snow(snow_intensity)
                        elif rain_intensity > 0:
                            stop_snow()
                            if not bird_eye:
                                start_rain(rain_intensity)
                        else:
                            stop_rain()
                            stop_snow()
                        set_wet("weather", precipitation, stage=stage)
                    except Exception:
                        pass
                    try:
                        from .fog_service import FogService
                        fog_intensity = preset.get("fog", 0.0)
                        FogService().set_fog(enabled=fog_intensity > 0, intensity=fog_intensity)
                    except Exception:
                        pass
                    print(f"[sky] Weather preset applied: {preset_key}")
                else:
                    print(f"[sky] Unknown weather preset: {preset_key}")

            if "weatherPreset" not in payload:
                MIN_DOME_INTENSITY = 0.5
                MIN_DISTANT_INTENSITY = 3000.0
                if dome_light_prim:
                    attr = dome_light_prim.GetAttribute("inputs:intensity")
                    if attr:
                        try:
                            val = attr.Get()
                            if val is not None and float(val) < MIN_DOME_INTENSITY:
                                set_attribute(dome_light_prim, "inputs:intensity", MIN_DOME_INTENSITY, float)
                        except (TypeError, ValueError):
                            set_attribute(dome_light_prim, "inputs:intensity", MIN_DOME_INTENSITY, float)
                    else:
                        set_attribute(dome_light_prim, "inputs:intensity", MIN_DOME_INTENSITY, float)
                if distant_light_prim:
                    attr = distant_light_prim.GetAttribute("inputs:intensity")
                    if attr:
                        try:
                            val = attr.Get()
                            if val is not None and float(val) < MIN_DISTANT_INTENSITY:
                                set_attribute(distant_light_prim, "inputs:intensity", MIN_DISTANT_INTENSITY, float)
                        except (TypeError, ValueError):
                            set_attribute(distant_light_prim, "inputs:intensity", MIN_DISTANT_INTENSITY, float)
                    else:
                        set_attribute(distant_light_prim, "inputs:intensity", MIN_DISTANT_INTENSITY, float)

        try:
            from omni.kit.viewport.utility import get_active_viewport

            viewport = get_active_viewport()
            if viewport:
                viewport.set_active_camera(viewport.get_active_camera())
        except Exception:
            pass

        if not distant_light_prim:
            return "no_light"
        print("[sky] Sky control applied")
        return "ok"

    except Exception as e:
        print(f"[sky] Error handling sky control: {e}")
        import traceback
        print(traceback.format_exc())
        return "no_env"

