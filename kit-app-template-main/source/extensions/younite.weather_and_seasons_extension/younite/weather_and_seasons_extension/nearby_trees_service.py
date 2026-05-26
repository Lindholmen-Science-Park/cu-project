"""
Nearby trees service — precomputes world-space tree positions from all
tile VEG PointInstancers and provides fast proximity lookups.

Scene composition note: city tiles use metersPerUnit=1, the main scene
uses metersPerUnit=0.01 (centimeters). The city scene prim has a 100x
unitsResolve scale, so 1 local tile unit = 100 world units.  All world
positions returned by this module are in the main scene's centimetre
coordinate system (matching GetLocalToWorldTransform on /World/PlayerCharacter).
"""

import math

from . import _shared

_tree_world_positions = None
_instancer_paths = None

_TREE_SHADER_SUFFIX = (
    "VEG_10500_Traed_genericTree/_materials/Tree_material/Image_Texture"
)

WORLD_UNITS_PER_METRE = 100.0

_get_stage = _shared.get_stage
get_player_pos = _shared.get_player_pos


def _compute_all_tree_world_positions(stage, shader_paths=None):
    """Iterate all tile VEG instancers and compute world-space position
    for every tree instance.  Returns ``(positions, instancer_paths)``."""
    from pxr import UsdGeom, Sdf, Usd, Gf

    PROTO_MARKER = "/Prototypes/"

    if shader_paths is None:
        shader_paths = []
        for prim in stage.Traverse():
            p = str(prim.GetPath())
            if p.endswith(_TREE_SHADER_SUFFIX):
                shader_paths.append(p)

    instancer_cache = {}
    skipped = []

    for sp in shader_paths:
        idx = sp.find(PROTO_MARKER)
        if idx < 0:
            continue
        inst_path = sp[:idx]

        if inst_path in instancer_cache:
            continue

        inst_prim = stage.GetPrimAtPath(inst_path)
        if not inst_prim or not inst_prim.IsValid():
            skipped.append((inst_path, "prim not found"))
            instancer_cache[inst_path] = []
            continue

        positions_attr = inst_prim.GetAttribute("positions")
        if not positions_attr or not positions_attr.HasValue():
            skipped.append((inst_path, "no positions attribute"))
            instancer_cache[inst_path] = []
            continue

        raw_positions = None
        for try_tc in [
            Usd.TimeCode(1.0),
            Usd.TimeCode(stage.GetStartTimeCode()),
            Usd.TimeCode.Default(),
        ]:
            raw_positions = positions_attr.Get(try_tc)
            if raw_positions is not None and len(raw_positions) > 0:
                break

        if raw_positions is None or len(raw_positions) == 0:
            skipped.append((inst_path, "positions empty at all time codes"))
            instancer_cache[inst_path] = []
            continue

        tc = Usd.TimeCode(1.0)
        xform_cache = UsdGeom.XformCache(tc)
        world_xform = xform_cache.GetLocalToWorldTransform(inst_prim)

        tile_positions = []
        for rp in raw_positions:
            wp = world_xform.Transform(
                Gf.Vec3d(float(rp[0]), float(rp[1]), float(rp[2]))
            )
            tile_positions.append(
                (float(wp[0]), float(wp[1]), float(wp[2]))
            )

        instancer_cache[inst_path] = tile_positions

    if skipped:
        for path, reason in skipped:
            print(f"[nearby_trees] SKIPPED {path}: {reason}")

    all_pos = []
    for pts in instancer_cache.values():
        all_pos.extend(pts)

    return all_pos, list(k for k, v in instancer_cache.items() if v)


def initialize(shader_paths=None):
    """Precompute all tree world positions.  Call once at season change."""
    global _tree_world_positions, _instancer_paths

    if _tree_world_positions is not None:
        return

    stage = _get_stage()
    if not stage:
        print("[nearby_trees] no stage available")
        return

    _tree_world_positions, _instancer_paths = (
        _compute_all_tree_world_positions(stage, shader_paths)
    )

    print(
        f"[nearby_trees] computed {len(_tree_world_positions)} tree world "
        f"positions from {len(_instancer_paths)} instancers"
    )

    player_pos = get_player_pos()
    print(
        f"[nearby_trees] player pos: "
        f"({player_pos[0]:.1f}, {player_pos[1]:.1f}, {player_pos[2]:.1f})"
    )

    if not _tree_world_positions:
        return

    bands_m = [5, 10, 25, 50, 100, 500]
    bands_wu = [b * WORLD_UNITS_PER_METRE for b in bands_m]
    counts = [0] * len(bands_m)
    min_dist = float("inf")
    nearest = None

    for tp in _tree_world_positions:
        dx = tp[0] - player_pos[0]
        dz = tp[2] - player_pos[2]
        d = math.sqrt(dx * dx + dz * dz)
        if d < min_dist:
            min_dist = d
            nearest = tp
        for bi, limit in enumerate(bands_wu):
            if d <= limit:
                counts[bi] += 1

    if nearest:
        print(
            f"[nearby_trees] nearest tree: "
            f"({nearest[0]:.1f}, {nearest[1]:.1f}, {nearest[2]:.1f}) "
            f"dist={min_dist:.0f} wu ({min_dist / WORLD_UNITS_PER_METRE:.1f} m)"
        )

    band_str = ", ".join(
        f"<{bm}m={c}" for bm, c in zip(bands_m, counts)
    )
    print(f"[nearby_trees] trees by distance: {band_str}")


def get_nearby_trees(radius):
    """Return list of ``(wx, wy, wz)`` for trees within *radius* (world
    units) of the player (XZ distance, ignores Y)."""
    if _tree_world_positions is None:
        return []

    px, _py, pz = get_player_pos()
    r_sq = radius * radius

    nearby = []
    for tx, ty, tz in _tree_world_positions:
        dx = tx - px
        dz = tz - pz
        if dx * dx + dz * dz <= r_sq:
            nearby.append((tx, ty, tz))

    return nearby


def invalidate_cache():
    """Clear the tree positions cache."""
    global _tree_world_positions, _instancer_paths
    _tree_world_positions = None
    _instancer_paths = None
