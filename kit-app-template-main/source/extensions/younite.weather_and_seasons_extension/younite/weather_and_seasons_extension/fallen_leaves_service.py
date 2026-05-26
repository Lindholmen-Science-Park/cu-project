"""
Falling leaves animation — PointInstancer driven, per-frame update.

When fall season is active, spawns leaf particles from the canopies of
nearby trees.  Leaves fall with gravity/wind/flutter, linger on the
ground, then get recycled.

Key behaviours:
- Leaves only spawn from real tree positions (nearby_trees_service).
- Distance culling: leaves too far from the player are recycled to
  nearby trees, so walking through the city always has leaf density.
- Staggered spawning prevents burst–pause cycles.
- Ground scatter is handled separately by ground_litter_service.
"""

import random
import math
import os

from . import _shared

_active = False
_update_sub = None
_positions = None
_speeds = None
_winds_x = None
_winds_z = None
_flutter_phases = None
_hit_floors = None
_scales = None
_ground_linger = None
_proto_indices = None
_orientations = None
_spin_speeds = None
_wait_timers = None
_leaf_count = 0

_nearby_trees_cache = []
_nearby_refresh_timer = 0.0

SYSTEM_ROOT = "/World/FallingLeavesSystem"

PROTO_PATHS = [
    f"{SYSTEM_ROOT}/Prototypes/LeafYellow",
    f"{SYSTEM_ROOT}/Prototypes/LeafOrange",
    f"{SYSTEM_ROOT}/Prototypes/LeafBrown",
    f"{SYSTEM_ROOT}/Prototypes/LeafRed",
]

INSTANCER_PATH = f"{SYSTEM_ROOT}/Instancer"

LEAF_COLORS = [
    (0.55, 0.40, 0.08),
    (0.50, 0.25, 0.05),
    (0.35, 0.20, 0.05),
    (0.45, 0.15, 0.04),
]

COLOR_WEIGHTS = [0.40, 0.30, 0.18, 0.12]

WU_PER_M = 100.0

LEAF_PROTO_SCALE = 0.004
MAX_LEAVES = 100

SPAWN_RADIUS = 100.0 * WU_PER_M
CULL_RADIUS = 60.0 * WU_PER_M

CANOPY_MIN_HEIGHT = 1.2 * WU_PER_M
CANOPY_MAX_HEIGHT = 3.0 * WU_PER_M
CANOPY_SCATTER = 0.8 * WU_PER_M

MIN_SPEED = 0.5
MAX_SPEED = 1.7

WIND_DRIFT = 0.3
FLUTTER_STRENGTH = 0.2

GROUND_LINGER_MIN = 45.0
GROUND_LINGER_MAX = 90.0

RESPAWN_DELAY_MIN = 5.0
RESPAWN_DELAY_MAX = 15.0

INITIAL_SPREAD = 180.0
RAYCAST_MAX_DIST = 20.0 * WU_PER_M
GROUND_Y_OFFSET = 3.0

NEARBY_REFRESH_INTERVAL = 3.0

_HIDDEN_Y = -999999.0


_get_stage = _shared.get_stage


def _raycast_floor_y(x, y_start, z, fallback_y):
    return _shared.raycast_floor_y(x, y_start, z, fallback_y, RAYCAST_MAX_DIST)


def _pick_color_index():
    r = random.random()
    total = 0.0
    for j, w in enumerate(COLOR_WEIGHTS):
        total += w
        if r <= total:
            return j
    return len(COLOR_WEIGHTS) - 1


def _random_orientation():
    ax = random.random() - 0.5
    ay = random.random() - 0.5
    az = random.random() - 0.5
    length = math.sqrt(ax * ax + ay * ay + az * az)
    if length < 1e-6:
        return (0.0, 0.0, 0.0, 1.0)
    ax /= length
    ay /= length
    az /= length
    angle = random.random() * math.tau
    s = math.sin(angle * 0.5)
    c = math.cos(angle * 0.5)
    return (ax * s, ay * s, az * s, c)


def _resolve_leaf_usd_path(stage):
    root_dir = os.path.dirname(stage.GetRootLayer().realPath)
    data_dir = os.path.normpath(os.path.join(root_dir, ".."))
    return os.path.normpath(
        os.path.join(data_dir, "Assets", "Maple_leaf", "Leaf.usd")
    )


def _create_leaf_prims(stage):
    from pxr import Usd, UsdGeom, Sdf, Gf

    leaf_usd = _resolve_leaf_usd_path(stage)
    if not os.path.isfile(leaf_usd):
        print(f"[falling_leaves] leaf asset not found: {leaf_usd}")
        return None

    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, Usd.EditTarget(session)):
        UsdGeom.Xform.Define(stage, SYSTEM_ROOT)

        s = LEAF_PROTO_SCALE
        for pp, color in zip(PROTO_PATHS, LEAF_COLORS):
            proto_xform = UsdGeom.Xform.Define(stage, pp)
            proto_xform.AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 96.93))
            proto_xform.AddScaleOp().Set(Gf.Vec3f(s, s, s))
            proto_prim = proto_xform.GetPrim()
            proto_prim.GetReferences().AddReference(leaf_usd)

        instancer = UsdGeom.PointInstancer.Define(stage, INSTANCER_PATH)
        instancer.GetPrim().CreateAttribute(
            "primvars:doNotCastShadows", Sdf.ValueTypeNames.Bool
        ).Set(True)
        instancer.CreatePrototypesRel().SetTargets(
            [Sdf.Path(p) for p in PROTO_PATHS]
        )

    color_ok = 0
    with Usd.EditContext(stage, Usd.EditTarget(session)):
        for pp, color in zip(PROTO_PATHS, LEAF_COLORS):
            shader_path = f"{pp}/Looks/leaf/leaf"
            shader_prim = stage.GetPrimAtPath(shader_path)
            if not shader_prim or not shader_prim.IsValid():
                print(f"[falling_leaves] WARNING: shader not found: {shader_path}")
                continue
            attr = shader_prim.GetAttribute("inputs:diffuse_color_constant")
            if attr:
                attr.Set(Gf.Vec3f(*color))
            metal = shader_prim.GetAttribute("inputs:metallic_constant")
            if metal:
                metal.Set(0.0)
            rough = shader_prim.GetAttribute("inputs:reflection_roughness_constant")
            if rough:
                rough.Set(1.0)
            color_ok += 1
    print(f"[falling_leaves] color overrides applied to {color_ok}/{len(PROTO_PATHS)} prototypes")

    prim = stage.GetPrimAtPath(INSTANCER_PATH)
    print(f"[falling_leaves] instancer created with real leaf mesh: "
          f"{prim and prim.IsValid()}")
    return instancer


def _make_leaf_data(tree_pos):
    """Build leaf data dict for a leaf at *tree_pos*."""
    tx, ty, tz = tree_pos

    x = tx + (random.random() - 0.5) * CANOPY_SCATTER * 2.0
    y = ty + CANOPY_MIN_HEIGHT + random.random() * (
        CANOPY_MAX_HEIGHT - CANOPY_MIN_HEIGHT
    )
    z = tz + (random.random() - 0.5) * CANOPY_SCATTER * 2.0

    floor_y = _raycast_floor_y(x, ty + 1.0 * WU_PER_M, z, ty) + GROUND_Y_OFFSET

    return {
        "pos": [x, y, z],
        "speed": MIN_SPEED + random.random() * (MAX_SPEED - MIN_SPEED),
        "wind_x": (random.random() - 0.5) * WIND_DRIFT,
        "wind_z": (random.random() - 0.5) * WIND_DRIFT,
        "flutter": random.random() * math.tau,
        "floor": floor_y,
        "scale": [
            0.8 + random.random() * 0.6,
            0.6 + random.random() * 0.4,
            0.8 + random.random() * 0.6,
        ],
        "proto": _pick_color_index(),
        "orient": _random_orientation(),
        "spin": (random.random() - 0.5) * 3.0,
    }


def _init_leaf_data(count, nearby_trees):
    """Populate per-leaf arrays — all start hidden with staggered timers."""
    global _positions, _speeds, _winds_x, _winds_z, _flutter_phases
    global _hit_floors, _scales, _ground_linger, _proto_indices
    global _orientations, _spin_speeds, _wait_timers

    _positions = []
    _speeds = []
    _winds_x = []
    _winds_z = []
    _flutter_phases = []
    _hit_floors = []
    _scales = []
    _ground_linger = []
    _proto_indices = []
    _orientations = []
    _spin_speeds = []
    _wait_timers = []

    if not nearby_trees:
        return 0

    for i in range(count):
        tree = random.choice(nearby_trees)
        d = _make_leaf_data(tree)

        d["pos"][1] = _HIDDEN_Y
        _ground_linger.append(0.0)
        _wait_timers.append(random.random() * INITIAL_SPREAD)

        _positions.append(d["pos"])
        _speeds.append(d["speed"])
        _winds_x.append(d["wind_x"])
        _winds_z.append(d["wind_z"])
        _flutter_phases.append(d["flutter"])
        _hit_floors.append(d["floor"])
        _scales.append(d["scale"])
        _proto_indices.append(d["proto"])
        _orientations.append(list(d["orient"]))
        _spin_speeds.append(d["spin"])

    return count


def _activate_leaf(i, nearby_trees):
    """Spawn leaf *i* from a nearby tree canopy."""
    if not nearby_trees:
        return

    tree = random.choice(nearby_trees)
    d = _make_leaf_data(tree)
    _positions[i] = d["pos"]
    _speeds[i] = d["speed"]
    _winds_x[i] = d["wind_x"]
    _winds_z[i] = d["wind_z"]
    _flutter_phases[i] = d["flutter"]
    _hit_floors[i] = d["floor"]
    _scales[i] = d["scale"]
    _ground_linger[i] = 0.0
    _proto_indices[i] = d["proto"]
    _orientations[i] = list(d["orient"])
    _spin_speeds[i] = d["spin"]
    _wait_timers[i] = 0.0


def _quat_multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _on_update(_event):
    global _nearby_trees_cache, _nearby_refresh_timer

    if not _active or _positions is None or len(_positions) == 0:
        return

    try:
        from pxr import Usd, UsdGeom, Vt, Gf

        stage = _get_stage()
        if not stage:
            return

        from . import nearby_trees_service
        player_pos = nearby_trees_service.get_player_pos()
        px, py, pz = player_pos

        dt_seconds = 1.0 / 60.0
        try:
            e_payload = getattr(_event, "payload", {})
            if isinstance(e_payload, dict):
                dt_val = e_payload.get("dt", 1.0 / 60.0)
            else:
                dt_val = 1.0 / 60.0
            dt_seconds = float(dt_val)
        except Exception:
            dt_seconds = 1.0 / 60.0

        dt = dt_seconds * 60.0

        _nearby_refresh_timer -= dt_seconds
        if _nearby_refresh_timer <= 0.0:
            _nearby_trees_cache = nearby_trees_service.get_nearby_trees(
                SPAWN_RADIUS
            )
            _nearby_refresh_timer = NEARBY_REFRESH_INTERVAL

        cull_r_sq = CULL_RADIUS * CULL_RADIUS

        for i in range(len(_positions)):
            p = _positions[i]

            # --- waiting to spawn ---
            if _wait_timers[i] > 0.0:
                _wait_timers[i] -= dt_seconds
                if _wait_timers[i] <= 0.0:
                    _activate_leaf(i, _nearby_trees_cache)
                else:
                    p[1] = _HIDDEN_Y
                continue

            # --- lingering on ground (never distance-culled) ---
            if _ground_linger[i] > 0.0:
                _ground_linger[i] -= dt_seconds
                p[1] = _hit_floors[i]
                if _ground_linger[i] <= 0.0:
                    _ground_linger[i] = 0.0
                    _wait_timers[i] = (
                        RESPAWN_DELAY_MIN
                        + random.random()
                        * (RESPAWN_DELAY_MAX - RESPAWN_DELAY_MIN)
                    )
                    p[1] = _HIDDEN_Y
                continue

            # --- distance cull (only for falling leaves, not ground) ---
            dx = p[0] - px
            dz = p[2] - pz
            if dx * dx + dz * dz > cull_r_sq:
                _wait_timers[i] = random.random() * 1.0
                p[1] = _HIDDEN_Y
                continue

            # --- falling ---
            p[1] -= _speeds[i] * dt
            p[0] += _winds_x[i] * dt
            p[2] += _winds_z[i] * dt

            _flutter_phases[i] += dt_seconds * 3.0
            p[0] += (
                math.sin(_flutter_phases[i])
                * FLUTTER_STRENGTH
                * dt
                * 0.08
            )
            p[2] += (
                math.cos(_flutter_phases[i] * 0.7)
                * FLUTTER_STRENGTH
                * 0.06
                * dt
            )

            spin_angle = _spin_speeds[i] * dt_seconds
            half = spin_angle * 0.5
            s = math.sin(half)
            c = math.cos(half)
            spin_q = (0.0, s, 0.0, c)
            _orientations[i] = list(
                _quat_multiply(spin_q, tuple(_orientations[i]))
            )

            if p[1] <= _hit_floors[i]:
                p[1] = _hit_floors[i]
                _ground_linger[i] = (
                    GROUND_LINGER_MIN
                    + random.random()
                    * (GROUND_LINGER_MAX - GROUND_LINGER_MIN)
                )

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            prim = stage.GetPrimAtPath(INSTANCER_PATH)
            if prim and prim.IsValid():
                inst = UsdGeom.PointInstancer(prim)
                inst.GetPositionsAttr().Set(
                    Vt.Vec3fArray(
                        [Gf.Vec3f(p[0], p[1], p[2]) for p in _positions]
                    )
                )
                inst.GetScalesAttr().Set(
                    Vt.Vec3fArray(
                        [Gf.Vec3f(s[0], s[1], s[2]) for s in _scales]
                    )
                )
                inst.GetOrientationsAttr().Set(
                    Vt.QuathArray(
                        [Gf.Quath(o[3], o[0], o[1], o[2])
                         for o in _orientations]
                    )
                )
    except Exception as e:
        print(f"[falling_leaves] update error: {e}")


def start_fallen_leaves(shader_paths=None):
    global _active, _update_sub, _leaf_count
    global _nearby_trees_cache, _nearby_refresh_timer

    if _active:
        return

    stage = _get_stage()
    if not stage:
        print("[falling_leaves] no stage available")
        return

    from . import nearby_trees_service
    nearby_trees_service.initialize(shader_paths)

    nearby_trees = nearby_trees_service.get_nearby_trees(SPAWN_RADIUS)
    _nearby_trees_cache = nearby_trees
    _nearby_refresh_timer = NEARBY_REFRESH_INTERVAL

    radius_m = SPAWN_RADIUS / WU_PER_M
    print(
        f"[falling_leaves] {len(nearby_trees)} trees within "
        f"{radius_m:.0f} m radius"
    )

    if not nearby_trees:
        print("[falling_leaves] no nearby trees — leaves will not appear")
        return

    _create_leaf_prims(stage)

    _leaf_count = MAX_LEAVES
    created = _init_leaf_data(_leaf_count, nearby_trees)

    if created == 0:
        print("[falling_leaves] no leaves created (no trees)")
        return

    from pxr import Usd, UsdGeom, Vt, Gf

    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, Usd.EditTarget(session)):
        prim = stage.GetPrimAtPath(INSTANCER_PATH)
        if prim and prim.IsValid():
            inst = UsdGeom.PointInstancer(prim)
            inst.GetPositionsAttr().Set(
                Vt.Vec3fArray(
                    [Gf.Vec3f(p[0], p[1], p[2]) for p in _positions]
                )
            )
            inst.GetScalesAttr().Set(
                Vt.Vec3fArray(
                    [Gf.Vec3f(s[0], s[1], s[2]) for s in _scales]
                )
            )
            inst.GetProtoIndicesAttr().Set(Vt.IntArray(_proto_indices))
            inst.GetOrientationsAttr().Set(
                Vt.QuathArray(
                    [Gf.Quath(o[3], o[0], o[1], o[2])
                     for o in _orientations]
                )
            )

    _active = True

    try:
        import carb.eventdispatcher
        import omni.kit.app

        ed = carb.eventdispatcher.get_eventdispatcher()
        _update_sub = ed.observe_event(
            observer_name=(
                "younite.weather_and_seasons_extension/falling_leaves/update"
            ),
            event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
            on_event=_on_update,
            order=0,
        )
    except Exception as e:
        print(f"[falling_leaves] failed to subscribe to updates: {e}")

    print(
        f"[falling_leaves] started — {_leaf_count} leaves "
        f"(staggered over {INITIAL_SPREAD:.0f}s), "
        f"cull at {CULL_RADIUS / WU_PER_M:.0f} m"
    )


def stop_fallen_leaves():
    global _active, _update_sub, _positions, _speeds
    global _winds_x, _winds_z, _flutter_phases, _hit_floors
    global _scales, _ground_linger, _proto_indices
    global _nearby_trees_cache, _nearby_refresh_timer
    global _orientations, _spin_speeds, _wait_timers

    if not _active:
        return

    _update_sub = None

    stage = _get_stage()
    if stage:
        try:
            from pxr import Sdf

            session = stage.GetSessionLayer()
            edit = Sdf.BatchNamespaceEdit()
            spec = session.GetPrimAtPath(SYSTEM_ROOT)
            if spec:
                edit.Add(Sdf.Path(SYSTEM_ROOT), Sdf.Path.emptyPath)
            session.Apply(edit)
        except Exception as e:
            print(f"[falling_leaves] cleanup error: {e}")

    _active = False
    _positions = None
    _speeds = None
    _winds_x = None
    _winds_z = None
    _flutter_phases = None
    _hit_floors = None
    _scales = None
    _ground_linger = None
    _proto_indices = None
    _orientations = None
    _spin_speeds = None
    _wait_timers = None
    _nearby_trees_cache = []
    _nearby_refresh_timer = 0.0

    print("[falling_leaves] stopped")


def invalidate_cache():
    from . import nearby_trees_service
    nearby_trees_service.invalidate_cache()
