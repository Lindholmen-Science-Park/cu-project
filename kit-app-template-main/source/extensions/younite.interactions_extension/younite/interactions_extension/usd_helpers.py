"""Stateless USD helper functions shared across the interactions extension.

All ``pxr`` / ``omni.usd`` imports stay inside function bodies (lazy imports),
matching the project-wide convention — module-level imports of pxr modules
have been known to trigger silent startup failures on some Kit versions.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

BoundsType = Tuple[Tuple[float, float, float], Tuple[float, float, float]]


def resolve_prim_position(
    prim_path: str,
    *,
    stage: Optional[Any] = None,
    xform_cache: Optional[Any] = None,
) -> Optional[Tuple[float, float, float]]:
    """Resolve a USD prim path to its world-space (x, y, z) position.

    For hot loops (many prims per frame), pass ``stage`` and a single
    ``UsdGeom.XformCache`` reused across calls — identical transforms, far
    less overhead than constructing a new cache per prim.
    """
    try:
        import omni.usd
        from pxr import Usd, UsdGeom

        if stage is None:
            stage = omni.usd.get_context().get_stage()
        if not stage:
            return None
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return None
        if xform_cache is None:
            xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        m = xform_cache.GetLocalToWorldTransform(prim)
        if hasattr(m, "ExtractTranslation"):
            t = m.ExtractTranslation()
            return (float(t[0]), float(t[1]), float(t[2]))
        return (float(m[3][0]), float(m[3][1]), float(m[3][2]))
    except Exception:
        return None


def resolve_prim_bounds(prim_path: str):
    """Resolve a USD prim to its world-space AABB: ((minX,minY,minZ),(maxX,maxY,maxZ))."""
    try:
        import omni.usd
        from pxr import Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return None, None
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return None, None
        imageable = UsdGeom.Imageable(prim)
        bbox = imageable.ComputeWorldBound(Usd.TimeCode.Default(), "default", "render")
        rng = bbox.GetRange()
        if rng.IsEmpty():
            return None, None
        mn = rng.GetMin()
        mx = rng.GetMax()
        bounds = (
            (float(mn[0]), float(mn[1]), float(mn[2])),
            (float(mx[0]), float(mx[1]), float(mx[2])),
        )
        center = (
            (bounds[0][0] + bounds[1][0]) / 2.0,
            (bounds[0][1] + bounds[1][1]) / 2.0,
            (bounds[0][2] + bounds[1][2]) / 2.0,
        )
        return center, bounds
    except Exception:
        return None, None


def resolve_prim_top(prim_path: str) -> Optional[Tuple[float, float, float]]:
    """Get the world-space top of a prim's Collider child cube.

    Convention: interactive prims have a child ``Cube "Collider"`` whose
    local-space top (0, 1, 0) maps to the display anchor above the object.
    """
    try:
        import omni.usd
        from pxr import Usd, UsdGeom, Gf

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return None
        collider = stage.GetPrimAtPath(f"{prim_path}/Collider")
        if not collider or not collider.IsValid():
            return None
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        l2w = cache.GetLocalToWorldTransform(collider)
        top = l2w.Transform(Gf.Vec3d(0, 1, 0))
        return (float(top[0]), float(top[1]), float(top[2]))
    except Exception:
        return None


def resolve_prim_path_from_config(pos_cfg: dict) -> str:
    """Resolve a prim path from position config, supporting both primPath and primName."""
    prim_path = str(pos_cfg.get("primPath") or "").strip()
    if not prim_path:
        prim_name = str(pos_cfg.get("primName") or "").strip()
        if prim_name:
            prim_path = f"/World/{prim_name}"
    return prim_path


def get_stage_meters_per_unit(stage) -> float:
    """Read metersPerUnit from the stage, falling back to 0.01 (1 cm)."""
    try:
        mpu = stage.GetMetadata("metersPerUnit")
        mpu = float(mpu) if mpu is not None else 0.01
        return mpu if mpu > 0 else 0.01
    except Exception:
        return 0.01


def stage_has_world_children() -> bool:
    """True if the stage is populated enough that ``/World`` has children.

    Used to suppress 'no Xforms match' warnings during the early pre-open
    load pass that happens before sublayers are composed.
    """
    try:
        import omni.usd

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return False
        world = stage.GetPrimAtPath("/World")
        if not world or not world.IsValid():
            return False
        return any(True for _ in world.GetAllChildren())
    except Exception:
        return False


def find_xforms_by_glob(pattern: str) -> list:
    """Recursively find prims under ``/World`` whose leaf name matches a glob.

    Returns a list of ``(prim_path, leaf_name)`` tuples.
    """
    import fnmatch

    try:
        import omni.usd

        stage = omni.usd.get_context().get_stage()
    except Exception:
        stage = None
    if stage is None:
        return []

    results: list = []
    try:
        world = stage.GetPrimAtPath("/World")
        if not world or not world.IsValid():
            return []
        for prim in world.GetAllChildren():
            results.extend(_collect_glob_matches(prim, pattern, fnmatch))
    except Exception:
        return []
    return results


def _collect_glob_matches(prim, pattern: str, fnmatch_mod) -> list:
    out: list = []
    try:
        name = prim.GetName()
        if fnmatch_mod.fnmatch(name, pattern):
            out.append((str(prim.GetPath()), name))
        for child in prim.GetAllChildren():
            out.extend(_collect_glob_matches(child, pattern, fnmatch_mod))
    except Exception:
        pass
    return out
