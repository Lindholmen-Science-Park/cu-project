"""
Snow via a single UsdGeomPointInstancer (session layer).

Prototype is `source/data/Assets/Snowflake/snowflake.usd` (referenced /World),
uniformly scaled to match the former sphere radius, with a simple white
UsdPreviewSurface bound in-session. Falls back to a procedural star mesh if
the asset path cannot be resolved.
"""

import os
import random
import math

from . import _shared

_instancer_prim = None
_update_sub = None
_positions = None
_speeds = None
_winds_x = None
_winds_z = None
_hit_floors = None
_scales = None
_scales_target = None
_flutter_phases = None
_ground_linger = None
_birth_times = None
_elapsed = 0.0
_intensity = 0.0
_flake_count = 0
_active = False

SNOW_ROOT = "/World/SnowSystem"
PROTO_PATH = f"{SNOW_ROOT}/Prototypes/Snowflake"
PROTO_REF_SUB = "Ref"
MATERIAL_PATH = f"{SNOW_ROOT}/Prototypes/SnowMaterial"
INSTANCER_PATH = f"{SNOW_ROOT}/Instancer"

# Relative to repo `data/` (see _resolve_snowflake_usd_path).
SNOWFLAKE_USD_REL = os.path.join("Assets", "Snowflake", "snowflake.usd")
# Composed /World bound from authoring file ≈ ±121 units; scale = FLAKE_RADIUS / half_extent.
SNOWFLAKE_ASSET_HALF_EXTENT = 121.25

VOLUME_RADIUS = 1500.0
VOLUME_HEIGHT = 2000.0
# Same as old sphere: UsdGeomSphere used GetRadiusAttr(FLAKE_RADIUS).
FLAKE_RADIUS = 0.78
# Applied to USD prototype scale and procedural mesh (1.0 = prior calibration).
SNOWFLAKE_SIZE_SCALE = 2.0
# Procedural fallback only: star tip radius = FLAKE_RADIUS × this × SNOWFLAKE_SIZE_SCALE.
SNOWFLAKE_MESH_RADIAL_SCALE = 1.2
SNOWFLAKE_VALLEY_FRAC = 0.42
MIN_FLAKE = 2500
MAX_FLAKE = 6000
MIN_SPEED = 6.0
MAX_SPEED = 16.0
WIND_DRIFT = 7.0
FLUTTER_STRENGTH = 4.0

GROUND_LINGER_MIN = 2.5
GROUND_LINGER_MAX = 5.0

FALLBACK_FLOOR_OFFSET = 200.0
RAYCAST_MAX_DIST = 8000.0

RAMP_DURATION = 5.0


_get_stage = _shared.get_stage
_get_player_pos = _shared.get_player_pos
_get_camera_forward_xz = _shared.get_camera_forward_xz


def _raycast_floor_y(x, y_start, z, fallback_y):
    return _shared.raycast_floor_y(x, y_start, z, fallback_y, RAYCAST_MAX_DIST)


def _resolve_snowflake_usd_path(stage):
    """Return absolute path to snowflake.usd, or None if not found."""
    candidates = []
    try:
        import omni.kit.app

        ext_mgr = omni.kit.app.get_app().get_extension_manager()
        ext_root = ext_mgr.get_extension_path("younite.weather_and_seasons_extension")
        if ext_root:
            candidates.append(
                os.path.normpath(os.path.join(ext_root, "..", "..", "data", SNOWFLAKE_USD_REL))
            )
    except Exception:
        pass
    try:
        root_layer = stage.GetRootLayer()
        lid = getattr(root_layer, "realPath", None) or root_layer.identifier
        if lid and not str(lid).startswith("anon:"):
            root_dir = os.path.dirname(str(lid))
            probe = root_dir
            for _ in range(12):
                if os.path.basename(probe) == "data":
                    candidates.append(os.path.normpath(os.path.join(probe, SNOWFLAKE_USD_REL)))
                    break
                parent = os.path.dirname(probe)
                if parent == probe:
                    break
                probe = parent
            candidates.append(os.path.normpath(os.path.join(root_dir, SNOWFLAKE_USD_REL)))
            candidates.append(os.path.normpath(os.path.join(root_dir, "..", SNOWFLAKE_USD_REL)))
    except Exception:
        pass
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        if os.path.isfile(c):
            return os.path.normpath(c).replace("\\", "/")
    return None


def _define_simple_white_material(stage):
    from pxr import UsdShade, Sdf, Gf

    mat = UsdShade.Material.Define(stage, MATERIAL_PATH)
    shader = UsdShade.Shader.Define(stage, f"{MATERIAL_PATH}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1.0, 1.0, 1.0))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _bind_white_material_to_meshes_under(stage, root_path: str):
    from pxr import Usd, UsdGeom, UsdShade

    root = stage.GetPrimAtPath(root_path)
    if not root or not root.IsValid():
        return
    mat_prim = stage.GetPrimAtPath(MATERIAL_PATH)
    if not mat_prim or not mat_prim.IsValid():
        return
    mat = UsdShade.Material(mat_prim)
    for prim in Usd.PrimRange(root):
        if prim.IsA(UsdGeom.Mesh):
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)


def _create_prototype_from_usd_asset(stage, asset_abs_path: str) -> None:
    from pxr import UsdGeom, Gf

    s = (float(FLAKE_RADIUS) / float(SNOWFLAKE_ASSET_HALF_EXTENT)) * float(SNOWFLAKE_SIZE_SCALE)
    xf = UsdGeom.Xform.Define(stage, PROTO_PATH)
    xf.ClearXformOpOrder()
    xf.AddScaleOp(precision=UsdGeom.XformOp.PrecisionFloat).Set(Gf.Vec3f(s, s, s))

    ref_path = f"{PROTO_PATH}/{PROTO_REF_SUB}"
    ref_prim = stage.DefinePrim(ref_path, "Xform")
    ref_prim.GetReferences().AddReference(assetPath=asset_abs_path, primPath="/World")

    _define_simple_white_material(stage)
    _bind_white_material_to_meshes_under(stage, PROTO_PATH)


def _snowflake_mesh_attrs():
    """Points, face counts, and indices for a 6-point star in XZ (y=0), double-sided."""
    from pxr import Gf, Vt

    R = FLAKE_RADIUS * SNOWFLAKE_MESH_RADIAL_SCALE * SNOWFLAKE_SIZE_SCALE
    r = R * SNOWFLAKE_VALLEY_FRAC
    pts = [Gf.Vec3f(0.0, 0.0, 0.0)]
    for i in range(6):
        a = i * math.pi / 3.0
        pts.append(Gf.Vec3f(R * math.cos(a), 0.0, R * math.sin(a)))
        a2 = (i + 0.5) * math.pi / 3.0
        pts.append(Gf.Vec3f(r * math.cos(a2), 0.0, r * math.sin(a2)))

    fvi = []
    for i in range(6):
        t = 1 + 2 * i
        v = 2 + 2 * i
        t2 = 1 + 2 * ((i + 1) % 6)
        fvi.extend((0, t, v, 0, v, t2))
    for i in range(6):
        t = 1 + 2 * i
        v = 2 + 2 * i
        t2 = 1 + 2 * ((i + 1) % 6)
        fvi.extend((0, v, t, 0, t2, v))

    ntri = len(fvi) // 3
    return Vt.Vec3fArray(pts), Vt.IntArray([3] * ntri), Vt.IntArray(fvi)


def _create_procedural_snowflake_prototype(stage):
    from pxr import UsdGeom, Vt, UsdShade

    _define_simple_white_material(stage)
    mesh = UsdGeom.Mesh.Define(stage, PROTO_PATH)
    pts, fcounts, findices = _snowflake_mesh_attrs()
    mesh.GetPointsAttr().Set(pts)
    mesh.GetFaceVertexCountsAttr().Set(fcounts)
    mesh.GetFaceVertexIndicesAttr().Set(findices)
    mesh.CreateSubdivisionSchemeAttr().Set("none")
    mesh.GetDisplayColorAttr().Set(Vt.Vec3fArray([(1.0, 1.0, 1.0)]))
    mat_prim = stage.GetPrimAtPath(MATERIAL_PATH)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(UsdShade.Material(mat_prim))


def _rand_pos(cx, cy, cz):
    angle = random.random() * math.tau
    dist = math.sqrt(random.random()) * VOLUME_RADIUS
    x = cx + math.cos(angle) * dist
    y = cy + random.random() * VOLUME_HEIGHT
    z = cz + math.sin(angle) * dist
    return (x, y, z)


def _create_snow_prims(stage, count):
    """Create prototype + instancer on the session layer.

    Positions and scales are written from the already-staggered module-level
    ``_positions`` / ``_scales`` arrays (set by ``_init_flake_data`` before this
    call) so the very first rendered frame matches the gentle steady-state.
    """
    from pxr import Usd, UsdGeom, Sdf, Vt, Gf

    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, Usd.EditTarget(session)):
        UsdGeom.Xform.Define(stage, SNOW_ROOT)

        asset_path = _resolve_snowflake_usd_path(stage)
        if asset_path:
            try:
                _create_prototype_from_usd_asset(stage, asset_path)
            except Exception as e:
                print(f"[snow] snowflake.usd failed ({e!s}); using procedural prototype")
                _create_procedural_snowflake_prototype(stage)
        else:
            print("[snow] snowflake.usd not found; using procedural prototype")
            _create_procedural_snowflake_prototype(stage)

        positions = [Gf.Vec3f(p[0], p[1], p[2]) for p in _positions]
        scales = [Gf.Vec3f(s[0], s[1], s[2]) for s in _scales]
        indices = [0] * count

        inst = UsdGeom.PointInstancer.Define(stage, INSTANCER_PATH)
        inst.GetPrim().CreateAttribute("primvars:doNotCastShadows", Sdf.ValueTypeNames.Bool).Set(True)
        inst.CreatePrototypesRel().SetTargets([PROTO_PATH])
        inst.GetPositionsAttr().Set(Vt.Vec3fArray(positions))
        inst.GetScalesAttr().Set(Vt.Vec3fArray(scales))
        inst.GetProtoIndicesAttr().Set(Vt.IntArray(indices))

    return inst


def _init_flake_data(count, center):
    global _positions, _speeds, _winds_x, _winds_z, _hit_floors
    global _scales, _scales_target, _flutter_phases, _ground_linger
    global _birth_times, _elapsed

    cx, cy, cz = center
    fallback_y = cy - FALLBACK_FLOOR_OFFSET
    _positions = [list(_rand_pos(cx, cy, cz)) for _ in range(count)]
    _speeds = [MIN_SPEED + random.random() * (MAX_SPEED - MIN_SPEED) for _ in range(count)]
    _winds_x = [(random.random() - 0.5) * WIND_DRIFT for _ in range(count)]
    _winds_z = [(random.random() - 0.5) * WIND_DRIFT for _ in range(count)]
    _hit_floors = [_raycast_floor_y(p[0], p[1], p[2], fallback_y) for p in _positions]
    _scales_target = []
    for _ in range(count):
        sx = 1.15 + random.random() * 0.45
        sy = 0.88 + random.random() * 0.28
        sz = 1.15 + random.random() * 0.45
        _scales_target.append([sx, sy, sz])
    _flutter_phases = [random.random() * math.tau for _ in range(count)]
    _ground_linger = [0.0] * count

    # Each flake gets a random birth time within [0, RAMP_DURATION].
    # Before its birth time the flake is invisible (scale 0).
    _birth_times = [random.random() * RAMP_DURATION for _ in range(count)]
    _elapsed = 0.0

    # All flakes start hidden; _on_update reveals them as _elapsed passes
    # their birth time.
    _scales = [[0.0, 0.0, 0.0] for _ in range(count)]

    # Stagger vertical positions so that when a flake is born it is already
    # at a natural height instead of always starting from the ceiling.
    for i in range(count):
        floor_y = _hit_floors[i]
        top_y = cy + VOLUME_HEIGHT
        _positions[i][1] = floor_y + random.random() * (top_y - floor_y)


def _respawn_flake_i(i, cx, cz, top_y, fallback_y):
    p = _positions[i]
    angle = random.random() * math.tau
    dist = math.sqrt(random.random()) * VOLUME_RADIUS
    p[0] = cx + math.cos(angle) * dist
    p[1] = top_y + random.random() * 400.0
    p[2] = cz + math.sin(angle) * dist
    _speeds[i] = MIN_SPEED + random.random() * (MAX_SPEED - MIN_SPEED)
    _winds_x[i] = (random.random() - 0.5) * WIND_DRIFT
    _winds_z[i] = (random.random() - 0.5) * WIND_DRIFT
    _flutter_phases[i] = random.random() * math.tau
    sx = 1.15 + random.random() * 0.45
    sy = 0.88 + random.random() * 0.28
    sz = 1.15 + random.random() * 0.45
    _scales_target[i] = [sx, sy, sz]
    _scales[i] = [sx, sy, sz]
    _hit_floors[i] = _raycast_floor_y(p[0], p[1], p[2], fallback_y)


def _on_update(_event):
    global _positions, _winds_x, _winds_z, _flutter_phases, _elapsed
    if not _active or _positions is None or _ground_linger is None:
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

        _elapsed += dt_seconds
        ramping = _elapsed < RAMP_DURATION

        fallback_y = cy - FALLBACK_FLOOR_OFFSET
        top_y = cy + VOLUME_HEIGHT

        for i in range(len(_positions)):
            if ramping and _elapsed < _birth_times[i]:
                continue

            if _scales[i][0] == 0.0 and _scales[i][1] == 0.0 and _scales[i][2] == 0.0:
                _scales[i][0] = _scales_target[i][0]
                _scales[i][1] = _scales_target[i][1]
                _scales[i][2] = _scales_target[i][2]

            p = _positions[i]
            _flutter_phases[i] += dt_seconds * 2.2

            if _ground_linger[i] > 0.0:
                _ground_linger[i] -= dt_seconds
                p[1] = _hit_floors[i]
                if _ground_linger[i] <= 0.0:
                    _ground_linger[i] = 0.0
                    _respawn_flake_i(i, cx, cz, top_y, fallback_y)
                continue

            wx = _winds_x[i] + math.sin(_flutter_phases[i] + i * 0.31) * FLUTTER_STRENGTH * 0.35
            wz = _winds_z[i] + math.cos(_flutter_phases[i] * 0.9 + i * 0.17) * FLUTTER_STRENGTH * 0.35
            _winds_x[i] += (random.random() - 0.5) * 0.55 * dt
            _winds_z[i] += (random.random() - 0.5) * 0.55 * dt
            _winds_x[i] = max(-WIND_DRIFT * 1.2, min(WIND_DRIFT * 1.2, _winds_x[i]))
            _winds_z[i] = max(-WIND_DRIFT * 1.2, min(WIND_DRIFT * 1.2, _winds_z[i]))

            p[1] -= _speeds[i] * dt
            p[0] += wx * dt
            p[2] += wz * dt

            p[0] += math.sin(_flutter_phases[i]) * FLUTTER_STRENGTH * 0.08 * dt
            p[2] += math.cos(_flutter_phases[i] * 1.1) * FLUTTER_STRENGTH * 0.08 * dt

            if p[1] <= _hit_floors[i]:
                p[1] = _hit_floors[i]
                _ground_linger[i] = GROUND_LINGER_MIN + random.random() * (
                    GROUND_LINGER_MAX - GROUND_LINGER_MIN
                )

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
        print(f"[snow] update error: {e}")


def start_snow(intensity: float):
    global _instancer_prim, _update_sub, _intensity, _flake_count, _active

    intensity = max(0.0, min(1.0, intensity))
    new_count = int(MIN_FLAKE + intensity * (MAX_FLAKE - MIN_FLAKE))

    if _active and new_count == _flake_count:
        return

    stop_snow()

    stage = _get_stage()
    if not stage:
        print("[snow] No stage available")
        return

    _intensity = intensity
    _flake_count = new_count
    px, py, pz = _get_player_pos()
    center = (px, py, pz)

    _init_flake_data(_flake_count, center)
    _instancer_prim = _create_snow_prims(stage, _flake_count)
    _active = True

    try:
        import carb.eventdispatcher
        import omni.kit.app
        ed = carb.eventdispatcher.get_eventdispatcher()
        _update_sub = ed.observe_event(
            observer_name="younite.weather_and_seasons_extension/snow_service/update",
            event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
            on_event=_on_update,
            order=0,
        )
    except Exception as e:
        print(f"[snow] Failed to subscribe to update loop: {e}")
        _active = False
        return

    print(f"[snow] Started — {_flake_count} flakes, intensity={_intensity:.2f}")


def stop_snow():
    global _instancer_prim, _update_sub, _positions, _speeds, _winds_x, _winds_z
    global _hit_floors, _scales, _scales_target, _flutter_phases, _ground_linger
    global _birth_times, _elapsed, _intensity, _flake_count, _active

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
                    stage.RemovePrim(Sdf.Path(SNOW_ROOT))
                except Exception:
                    try:
                        edit = Sdf.BatchNamespaceEdit()
                        edit.Add(Sdf.Path(SNOW_ROOT), Sdf.Path.emptyPath)
                        session.Apply(edit)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[snow] cleanup error: {e}")

    if was_active:
        print("[snow] Stopped")

    _instancer_prim = None
    _positions = None
    _speeds = None
    _winds_x = None
    _winds_z = None
    _hit_floors = None
    _scales = None
    _scales_target = None
    _flutter_phases = None
    _ground_linger = None
    _birth_times = None
    _elapsed = 0.0
    _intensity = 0.0
    _flake_count = 0
