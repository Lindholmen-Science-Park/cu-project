"""
Ground leaf litter — static leaves scattered around nearby trees.

A separate PointInstancer system from the falling-leaf animation.
Maintains a pool of leaf instances on the ground in concentric rings
around trees near the player.  As the player moves, distant litter is
recycled to trees that have come into range.

Uses its own instancer at /World/GroundLitterSystem, independent from
the falling-leaves instancer at /World/FallingLeavesSystem.
"""

import random
import math
import os

from . import _shared

_active = False
_update_sub = None

_positions = None
_floors = None
_scales = None
_proto_indices = None
_orientations = None

_litter_count = 0
_refresh_timer = 0.0

WU_PER_M = 100.0

MAX_LITTER = 2400

POPULATE_RADIUS = 80.0 * WU_PER_M
CULL_RADIUS = 90.0 * WU_PER_M

GROUND_INNER_RADIUS = 3.0 * WU_PER_M
GROUND_INNER_FRAC = 0.55
GROUND_MID_RADIUS = 8.0 * WU_PER_M
GROUND_MID_FRAC = 0.30
GROUND_OUTER_RADIUS = 15.0 * WU_PER_M

RAYCAST_MAX_DIST = 20.0 * WU_PER_M
GROUND_Y_OFFSET = 3.0

REFRESH_INTERVAL = 2.0

SYSTEM_ROOT = "/World/GroundLitterSystem"
INSTANCER_PATH = f"{SYSTEM_ROOT}/Instancer"

PROTO_PATHS = [
    f"{SYSTEM_ROOT}/Prototypes/LeafYellow",
    f"{SYSTEM_ROOT}/Prototypes/LeafOrange",
    f"{SYSTEM_ROOT}/Prototypes/LeafBrown",
    f"{SYSTEM_ROOT}/Prototypes/LeafRed",
]

LEAF_COLORS = [
    (0.55, 0.40, 0.08),
    (0.50, 0.25, 0.05),
    (0.35, 0.20, 0.05),
    (0.45, 0.15, 0.04),
]
COLOR_WEIGHTS = [0.40, 0.30, 0.18, 0.12]

LEAF_PROTO_SCALE = 0.004

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


def _random_flat_orientation():
    """Random rotation roughly flat on the ground (Y-axis spin + slight tilt)."""
    yaw = random.random() * math.tau
    tilt = (random.random() - 0.5) * 0.5
    sy = math.sin(yaw * 0.5)
    cy = math.cos(yaw * 0.5)
    st = math.sin(tilt * 0.5)
    ct = math.cos(tilt * 0.5)
    return (st * cy, sy * ct, -st * sy, ct * cy)


def _ring_offset(tx, tz):
    """Pick random XZ in concentric rings around (tx, tz)."""
    r = random.random()
    if r < GROUND_INNER_FRAC:
        radius = random.random() * GROUND_INNER_RADIUS
    elif r < GROUND_INNER_FRAC + GROUND_MID_FRAC:
        radius = (
            GROUND_INNER_RADIUS
            + random.random() * (GROUND_MID_RADIUS - GROUND_INNER_RADIUS)
        )
    else:
        radius = (
            GROUND_MID_RADIUS
            + random.random() * (GROUND_OUTER_RADIUS - GROUND_MID_RADIUS)
        )
    angle = random.random() * math.tau
    return tx + math.cos(angle) * radius, tz + math.sin(angle) * radius


def _resolve_leaf_usd_path(stage):
    root_dir = os.path.dirname(stage.GetRootLayer().realPath)
    data_dir = os.path.normpath(os.path.join(root_dir, ".."))
    return os.path.normpath(
        os.path.join(data_dir, "Assets", "Maple_leaf", "Leaf.usd")
    )


def _create_litter_prims(stage):
    from pxr import Usd, UsdGeom, Sdf, Gf

    leaf_usd = _resolve_leaf_usd_path(stage)
    if not os.path.isfile(leaf_usd):
        print(f"[ground_litter] leaf asset not found: {leaf_usd}")
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
                print(f"[ground_litter] WARNING: shader not found: {shader_path}")
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
    print(f"[ground_litter] color overrides applied to {color_ok}/{len(PROTO_PATHS)} prototypes")

    print(f"[ground_litter] instancer created with real leaf mesh")
    return instancer


def _place_leaf_at_tree(tree_pos):
    """Create one ground leaf near *tree_pos*."""
    tx, ty, tz = tree_pos
    gx, gz = _ring_offset(tx, tz)
    floor_y = _raycast_floor_y(gx, ty + 1.0 * WU_PER_M, gz, ty) + GROUND_Y_OFFSET
    return {
        "pos": [gx, floor_y, gz],
        "floor": floor_y,
        "scale": [
            0.8 + random.random() * 0.6,
            0.6 + random.random() * 0.4,
            0.8 + random.random() * 0.6,
        ],
        "proto": _pick_color_index(),
        "orient": _random_flat_orientation(),
    }


def _init_litter(count, nearby_trees):
    """Fill all litter slots with leaves on the ground near trees."""
    global _positions, _floors, _scales, _proto_indices, _orientations

    _positions = []
    _floors = []
    _scales = []
    _proto_indices = []
    _orientations = []

    if not nearby_trees:
        return 0

    for _i in range(count):
        tree = random.choice(nearby_trees)
        d = _place_leaf_at_tree(tree)
        _positions.append(d["pos"])
        _floors.append(d["floor"])
        _scales.append(d["scale"])
        _proto_indices.append(d["proto"])
        _orientations.append(list(d["orient"]))

    return count


def _flush_to_instancer(stage):
    """Push current arrays to the USD instancer."""
    from pxr import Usd, UsdGeom, Vt, Gf

    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, Usd.EditTarget(session)):
        prim = stage.GetPrimAtPath(INSTANCER_PATH)
        if not prim or not prim.IsValid():
            return
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
                [Gf.Quath(o[3], o[0], o[1], o[2]) for o in _orientations]
            )
        )
        inst.GetProtoIndicesAttr().Set(Vt.IntArray(_proto_indices))


def _on_update(_event):
    """Periodic check: cull distant litter, populate near new trees."""
    global _refresh_timer

    if not _active or _positions is None:
        return

    try:
        dt_seconds = 1.0 / 60.0
        try:
            e_payload = getattr(_event, "payload", {})
            if isinstance(e_payload, dict):
                dt_seconds = float(e_payload.get("dt", 1.0 / 60.0))
        except Exception:
            pass

        _refresh_timer -= dt_seconds
        if _refresh_timer > 0.0:
            return
        _refresh_timer = REFRESH_INTERVAL

        from . import nearby_trees_service
        px, py, pz = nearby_trees_service.get_player_pos()

        cull_r_sq = CULL_RADIUS * CULL_RADIUS

        free_slots = []
        for i in range(len(_positions)):
            p = _positions[i]
            if p[1] == _HIDDEN_Y:
                free_slots.append(i)
                continue
            dx = p[0] - px
            dz = p[2] - pz
            if dx * dx + dz * dz > cull_r_sq:
                _positions[i][1] = _HIDDEN_Y
                free_slots.append(i)

        if not free_slots:
            _flush_to_instancer(_get_stage())
            return

        nearby = nearby_trees_service.get_nearby_trees(POPULATE_RADIUS)
        if not nearby:
            _flush_to_instancer(_get_stage())
            return

        for slot in free_slots:
            tree = random.choice(nearby)
            d = _place_leaf_at_tree(tree)
            _positions[slot] = d["pos"]
            _floors[slot] = d["floor"]
            _scales[slot] = d["scale"]
            _proto_indices[slot] = d["proto"]
            _orientations[slot] = list(d["orient"])

        stage = _get_stage()
        if stage:
            _flush_to_instancer(stage)

    except Exception as e:
        print(f"[ground_litter] update error: {e}")


def start(shader_paths=None):
    """Start the ground litter system."""
    global _active, _update_sub, _litter_count, _refresh_timer

    if _active:
        return

    stage = _get_stage()
    if not stage:
        return

    from . import nearby_trees_service
    nearby_trees_service.initialize(shader_paths)

    nearby = nearby_trees_service.get_nearby_trees(POPULATE_RADIUS)
    if not nearby:
        print("[ground_litter] no nearby trees")
        return

    _create_litter_prims(stage)

    _litter_count = MAX_LITTER
    _init_litter(_litter_count, nearby)
    _flush_to_instancer(stage)
    _refresh_timer = REFRESH_INTERVAL

    _active = True

    try:
        import carb.eventdispatcher
        import omni.kit.app
        ed = carb.eventdispatcher.get_eventdispatcher()
        _update_sub = ed.observe_event(
            observer_name="younite.weather_and_seasons_extension/ground_litter/update",
            event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
            on_event=_on_update,
            order=0,
        )
    except Exception as e:
        print(f"[ground_litter] subscribe error: {e}")

    print(f"[ground_litter] started — {_litter_count} leaves around "
          f"{len(nearby)} trees")


def stop():
    """Stop and clean up."""
    global _active, _update_sub, _positions, _floors, _scales
    global _proto_indices, _orientations

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
            print(f"[ground_litter] cleanup error: {e}")

    _active = False
    _positions = None
    _floors = None
    _scales = None
    _proto_indices = None
    _orientations = None

    print("[ground_litter] stopped")
