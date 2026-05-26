"""
Rain effect via UsdGeomPointInstancer.

Creates a PointInstancer with small sphere prototypes on the session layer.
A per-frame update subscription animates positions downward.  Each drop has
a per-drop "floor Y" determined by a downward PhysX raycast at spawn time;
when a drop reaches its floor (ground, roof collider, etc.) it respawns at
the top of the volume.  This means rain naturally stops at any collider —
add a collider to the roof and drops will disappear there while remaining
visible outside.
"""

import random
import math

from . import _shared

_instancer_prim = None
_update_sub = None
_positions = None
_speeds = None
_winds = None
_hit_floors = None
_scales = None
_splash_timers = None
_intensity = 0.0
_drop_count = 0
_active = False

RAIN_ROOT = "/World/RainSystem"
PROTO_PATH = f"{RAIN_ROOT}/Prototypes/Raindrop"
MATERIAL_PATH = f"{RAIN_ROOT}/Prototypes/RainMaterial"
INSTANCER_PATH = f"{RAIN_ROOT}/Instancer"

VOLUME_HALF_FWD = 750.0
VOLUME_HALF_SIDE = 1000.0
VOLUME_HEIGHT = 3000.0
DROP_RADIUS = 0.4
MIN_DROPS = 400
MAX_DROPS = 1000
MIN_SPEED = 80.0
MAX_SPEED = 140.0
WIND_BIAS = 3.0

FALLBACK_FLOOR_OFFSET = 200.0
RAYCAST_MAX_DIST = 8000.0

FORWARD_BIAS = 900.0

SPLASH_DURATION = 0.15
SPLASH_MAX_XZ = 9.0
SPLASH_MIN_Y = 0.15


_get_stage = _shared.get_stage
_get_player_pos = _shared.get_player_pos
_get_camera_forward_xz = _shared.get_camera_forward_xz


def _raycast_floor_y(x, y_start, z, fallback_y):
    return _shared.raycast_floor_y(x, y_start, z, fallback_y, RAYCAST_MAX_DIST)


def _rand_pos(cx, cy, cz, fwd_x=0.0, fwd_z=1.0):
    """Random position in a camera-aligned rectangle above the player."""
    right_x = -fwd_z
    right_z = fwd_x
    fwd_off = (random.random() - 0.5) * 2.0 * VOLUME_HALF_FWD
    side_off = (random.random() - 0.5) * 2.0 * VOLUME_HALF_SIDE
    x = cx + fwd_x * fwd_off + right_x * side_off
    y = cy + random.random() * VOLUME_HEIGHT
    z = cz + fwd_z * fwd_off + right_z * side_off
    return (x, y, z)


def _create_rain_prims(stage, count, center):
    """Create the PointInstancer, prototype sphere, and material on the session layer."""
    from pxr import Usd, UsdGeom, UsdShade, Sdf, Vt, Gf

    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, Usd.EditTarget(session)):
        scope = UsdGeom.Xform.Define(stage, RAIN_ROOT)

        sphere = UsdGeom.Sphere.Define(stage, PROTO_PATH)
        sphere.GetRadiusAttr().Set(DROP_RADIUS)
        sphere.GetDisplayColorAttr().Set(Vt.Vec3fArray([(0.68, 0.76, 0.88)]))

        mat = UsdShade.Material.Define(stage, MATERIAL_PATH)
        shader = UsdShade.Shader.Define(stage, f"{MATERIAL_PATH}/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.68, 0.76, 0.88))
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.3)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.1)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(sphere.GetPrim()).Bind(mat)

        instancer = UsdGeom.PointInstancer.Define(stage, INSTANCER_PATH)
        instancer.GetPrim().CreateAttribute("primvars:doNotCastShadows", Sdf.ValueTypeNames.Bool).Set(True)
        instancer.CreatePrototypesRel().SetTargets([PROTO_PATH])

        cx, cy, cz = center
        fwd_x, fwd_z = _get_camera_forward_xz()
        positions = []
        scales = []
        indices = []
        for _ in range(count):
            positions.append(Gf.Vec3f(*_rand_pos(cx, cy, cz, fwd_x, fwd_z)))
            y_stretch = 2.0 + random.random() * 2.0
            scales.append(Gf.Vec3f(1.0, y_stretch, 1.0))
            indices.append(0)

        instancer.GetPositionsAttr().Set(Vt.Vec3fArray(positions))
        instancer.GetScalesAttr().Set(Vt.Vec3fArray(scales))
        instancer.GetProtoIndicesAttr().Set(Vt.IntArray(indices))

    return instancer


def _init_drop_data(count, center):
    """Initialise per-drop arrays (positions, speeds, wind drift, floor heights, scales, splash timers)."""
    global _positions, _speeds, _winds, _hit_floors, _scales, _splash_timers
    cx, cy, cz = center
    fwd_x, fwd_z = _get_camera_forward_xz()
    fallback_y = cy - FALLBACK_FLOOR_OFFSET
    _positions = [list(_rand_pos(cx, cy, cz, fwd_x, fwd_z)) for _ in range(count)]
    _speeds = [MIN_SPEED + random.random() * (MAX_SPEED - MIN_SPEED) for _ in range(count)]
    _winds = [(random.random() - 0.3) * WIND_BIAS for _ in range(count)]
    _hit_floors = [
        _raycast_floor_y(p[0], p[1], p[2], fallback_y) for p in _positions
    ]
    _scales = [[1.0, 2.0 + random.random() * 2.0, 1.0] for _ in range(count)]
    _splash_timers = [0.0] * count


def _on_update(_event):
    """Per-frame rain animation: move drops down, run splash morph at
    ground contact, respawn at top biased toward camera forward."""
    global _positions, _scales, _splash_timers
    if not _active or _positions is None:
        return

    try:
        from pxr import Usd, UsdGeom, Vt, Gf

        stage = _get_stage()
        if not stage:
            return

        cx, cy, cz = _get_player_pos()

        dt = 1.0
        dt_seconds = 1.0 / 60.0
        try:
            e_payload = getattr(_event, "payload", {})
            if isinstance(e_payload, dict):
                dt_val = e_payload.get("dt", 1.0 / 60.0)
            else:
                dt_val = 1.0 / 60.0
            dt_seconds = float(dt_val)
            dt = dt_seconds * 60.0
        except Exception:
            dt = 1.0
            dt_seconds = 1.0 / 60.0

        fwd_x, fwd_z = _get_camera_forward_xz()
        biased_cx = cx + fwd_x * FORWARD_BIAS
        biased_cz = cz + fwd_z * FORWARD_BIAS
        right_x = -fwd_z
        right_z = fwd_x

        fallback_y = cy - FALLBACK_FLOOR_OFFSET
        top_y = cy + VOLUME_HEIGHT

        for i in range(len(_positions)):
            p = _positions[i]
            s = _scales[i]

            if _splash_timers[i] > 0.0:
                _splash_timers[i] -= dt_seconds
                if _splash_timers[i] <= 0.0:
                    _splash_timers[i] = 0.0
                    fwd_off = (random.random() - 0.5) * 2.0 * VOLUME_HALF_FWD
                    side_off = (random.random() - 0.5) * 2.0 * VOLUME_HALF_SIDE
                    p[0] = biased_cx + fwd_x * fwd_off + right_x * side_off
                    p[1] = top_y + random.random() * 400.0
                    p[2] = biased_cz + fwd_z * fwd_off + right_z * side_off
                    _speeds[i] = MIN_SPEED + random.random() * (MAX_SPEED - MIN_SPEED)
                    _winds[i] = (random.random() - 0.3) * WIND_BIAS
                    y_stretch = 2.0 + random.random() * 2.0
                    s[0] = 1.0
                    s[1] = y_stretch
                    s[2] = 1.0
                    _hit_floors[i] = _raycast_floor_y(p[0], p[1], p[2], fallback_y)
                else:
                    t = 1.0 - (_splash_timers[i] / SPLASH_DURATION)
                    s[0] = 1.0 + t * (SPLASH_MAX_XZ - 1.0)
                    s[1] = max(SPLASH_MIN_Y, s[1] * (1.0 - t) + SPLASH_MIN_Y * t)
                    s[2] = s[0]
            else:
                p[1] -= _speeds[i] * dt
                p[0] += _winds[i] * dt

                if p[1] < _hit_floors[i]:
                    p[1] = _hit_floors[i]
                    _splash_timers[i] = SPLASH_DURATION

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            prim = stage.GetPrimAtPath(INSTANCER_PATH)
            if prim and prim.IsValid():
                inst = UsdGeom.PointInstancer(prim)
                inst.GetPositionsAttr().Set(
                    Vt.Vec3fArray([Gf.Vec3f(p[0], p[1], p[2]) for p in _positions])
                )
                inst.GetScalesAttr().Set(
                    Vt.Vec3fArray([Gf.Vec3f(s[0], s[1], s[2]) for s in _scales])
                )
    except Exception as e:
        print(f"[rain] update error: {e}")


def start_rain(intensity: float):
    """Start or update rain. intensity 0-1 controls drop count."""
    global _instancer_prim, _update_sub, _intensity, _drop_count, _active, _hit_floors

    intensity = max(0.0, min(1.0, intensity))
    new_count = int(MIN_DROPS + intensity * (MAX_DROPS - MIN_DROPS))

    if _active and new_count == _drop_count:
        return

    stop_rain()

    stage = _get_stage()
    if not stage:
        print("[rain] No stage available")
        return

    _intensity = intensity
    _drop_count = new_count
    px, py, pz = _get_player_pos()
    fwd_x, fwd_z = _get_camera_forward_xz()
    center = (px + fwd_x * FORWARD_BIAS, py, pz + fwd_z * FORWARD_BIAS)

    _instancer_prim = _create_rain_prims(stage, _drop_count, center)
    _init_drop_data(_drop_count, center)
    _active = True

    try:
        import carb.eventdispatcher
        import omni.kit.app
        ed = carb.eventdispatcher.get_eventdispatcher()
        _update_sub = ed.observe_event(
            observer_name="younite.weather_and_seasons_extension/rain_service/update",
            event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
            on_event=_on_update,
            order=0,
        )
    except Exception as e:
        print(f"[rain] Failed to subscribe to update loop: {e}")
        _active = False
        return

    print(f"[rain] Started — {_drop_count} drops, intensity={_intensity:.2f}")


def stop_rain():
    """Stop rain and clean up session-layer prims."""
    global _instancer_prim, _update_sub, _positions, _speeds, _winds, _hit_floors
    global _scales, _splash_timers, _intensity, _drop_count, _active

    was_active = _active
    _active = False

    _update_sub = None

    stage = _get_stage()
    if stage:
        try:
            from pxr import Usd, UsdGeom, Sdf, Vt
            session = stage.GetSessionLayer()

            with Usd.EditContext(stage, Usd.EditTarget(session)):
                prim = stage.GetPrimAtPath(INSTANCER_PATH)
                if prim and prim.IsValid():
                    inst = UsdGeom.PointInstancer(prim)
                    inst.GetPositionsAttr().Set(Vt.Vec3fArray())
                    inst.GetProtoIndicesAttr().Set(Vt.IntArray())
                    inst.GetScalesAttr().Set(Vt.Vec3fArray())
                try:
                    stage.RemovePrim(Sdf.Path(RAIN_ROOT))
                except Exception:
                    try:
                        edit = Sdf.BatchNamespaceEdit()
                        edit.Add(Sdf.Path(RAIN_ROOT), Sdf.Path.emptyPath)
                        session.Apply(edit)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[rain] cleanup error: {e}")

    if was_active:
        print("[rain] Stopped")

    _instancer_prim = None
    _positions = None
    _speeds = None
    _winds = None
    _hit_floors = None
    _scales = None
    _splash_timers = None
    _intensity = 0.0
    _drop_count = 0
