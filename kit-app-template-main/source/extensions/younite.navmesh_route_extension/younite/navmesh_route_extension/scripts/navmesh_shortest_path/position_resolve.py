"""Resolve prim paths or numeric triples to world-space positions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .types import Vec3Ref

if TYPE_CHECKING:
    from pxr import Gf


def _to_gf_vec3d(value: Vec3Ref) -> "Gf.Vec3d":
    from pxr import Gf

    if isinstance(value, Gf.Vec3d):
        return value
    if isinstance(value, Gf.Vec3f):
        return Gf.Vec3d(float(value[0]), float(value[1]), float(value[2]))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return Gf.Vec3d(float(value[0]), float(value[1]), float(value[2]))
    raise TypeError(f"Unsupported Vec3Ref type: {type(value)}")


def resolve_spawn_prim_path_by_leaf_name(stage, leaf_name: str) -> Optional[str]:
    """Resolve a spawn prim path when only the leaf name is known.

    Tries ``/World/<leaf>`` first (flat spawns). If missing, searches the
    ``/World`` subtree for a prim whose name equals ``leaf_name`` so nested
    NPC meet points (e.g. ``/World/Red/PlayerSpawnPoint_Red``) resolve the
    same way as ``/World/PlayerSpawnPoint_Foyer``.
    """
    from pxr import Usd, UsdGeom

    leaf = str(leaf_name or "").strip()
    if not leaf:
        return None
    direct = f"/World/{leaf}"
    prim = stage.GetPrimAtPath(direct)
    if prim and prim.IsValid():
        return direct
    world = stage.GetPrimAtPath("/World")
    if not (world and world.IsValid()):
        return None
    for p in Usd.PrimRange(world):
        if not p.IsValid():
            continue
        if p.GetName() != leaf:
            continue
        if not p.IsA(UsdGeom.Xform):
            continue
        return str(p.GetPath())
    return None


def get_world_translation(stage, prim_path: str) -> "Gf.Vec3d":
    """World translation of a prim at default time."""
    from pxr import Gf, Usd, UsdGeom

    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"Prim not found: {prim_path}")

    xform = UsdGeom.Xformable(prim)
    if not xform:
        raise RuntimeError(f"Prim is not Xformable: {prim_path}")

    mat = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    t = mat.ExtractTranslation()
    return Gf.Vec3d(t[0], t[1], t[2])


def get_ground_position(stage, prim_path: str) -> "Gf.Vec3d":
    """
    Ground position by raycasting downward from the prim's origin.
    Falls back to world translation if PhysX is unavailable.
    """
    from pxr import Gf

    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"Prim not found: {prim_path}")

    world_pos = get_world_translation(stage, prim_path)

    try:
        import omni.physx
        import carb._carb as _carb_c

        sqi = omni.physx.get_physx_scene_query_interface()
        if sqi:
            ray_start_offset = 50.0
            ray_origin = _carb_c.Float3(float(world_pos[0]), float(world_pos[1] + ray_start_offset), float(world_pos[2]))
            ray_direction = _carb_c.Float3(0.0, -1.0, 0.0)
            max_distance = 500.0

            hit_result = sqi.raycast_closest(ray_origin, ray_direction, float(max_distance), bool(True))

            if hit_result and hit_result.get("hit", False):
                hit_pos = hit_result.get("position")
                if hit_pos:
                    try:
                        if isinstance(hit_pos, (list, tuple)) and len(hit_pos) >= 3:
                            return Gf.Vec3d(float(hit_pos[0]), float(hit_pos[1]), float(hit_pos[2]))
                        elif hasattr(hit_pos, "__getitem__"):
                            x = float(hit_pos[0]) if len(hit_pos) > 0 else world_pos[0]
                            y = float(hit_pos[1]) if len(hit_pos) > 1 else world_pos[1]
                            z = float(hit_pos[2]) if len(hit_pos) > 2 else world_pos[2]
                            return Gf.Vec3d(x, y, z)
                    except (IndexError, TypeError, ValueError):
                        pass
    except Exception:
        pass

    return world_pos


def resolve_position(stage, ref: Vec3Ref, *, use_ground: bool = False) -> "Gf.Vec3d":
    """
    Resolve a start/end reference into a world position.

    - ``str`` prim path: world translation, optionally ground-projected
    - vec / sequence: treated as world position
    """
    if isinstance(ref, str):
        return get_ground_position(stage, ref) if use_ground else get_world_translation(stage, ref)
    return _to_gf_vec3d(ref)
