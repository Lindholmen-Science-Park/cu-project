"""
Shared utilities for all seasons/weather services.

Centralises functions that were previously duplicated across snow, rain,
fallen-leaves, ground-litter, and nearby-trees modules.
"""

import math


def get_stage():
    """Return the current USD stage, or None."""
    try:
        import omni.usd
        ctx = omni.usd.get_context()
        return ctx.get_stage() if ctx else None
    except Exception:
        return None


def get_player_pos():
    """Player world position via XformCache.  Falls back to (0, 2300, 0)."""
    try:
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return (0.0, 2300.0, 0.0)
        prim = stage.GetPrimAtPath("/World/PlayerCharacter")
        if prim and prim.IsValid():
            from pxr import UsdGeom, Usd
            cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            m = cache.GetLocalToWorldTransform(prim)
            t = m.ExtractTranslation()
            return (float(t[0]), float(t[1]), float(t[2]))
    except Exception:
        pass
    return (0.0, 2300.0, 0.0)


def raycast_floor_y(x, y_start, z, fallback_y, max_dist=8000.0):
    """Downward PhysX raycast — returns the Y where a collider is hit, or fallback_y."""
    try:
        import omni.physx
        import carb._carb as _carb_c

        sqi = omni.physx.get_physx_scene_query_interface()
        if not sqi:
            return fallback_y

        origin = _carb_c.Float3(float(x), float(y_start), float(z))
        direction = _carb_c.Float3(0.0, -1.0, 0.0)
        hit = sqi.raycast_closest(origin, direction, max_dist, True)
        if hit and hit.get("hit", False):
            pos = hit.get("position")
            if pos is not None and hasattr(pos, "__getitem__"):
                return float(pos[1])
    except Exception:
        pass
    return fallback_y


def get_camera_forward_xz():
    """Camera forward direction projected onto XZ plane (normalised)."""
    try:
        import omni.kit.viewport.utility
        from pxr import UsdGeom, Usd
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if not viewport:
            return (0.0, 1.0)
        camera_path = viewport.get_active_camera()
        stage = get_stage()
        if not stage:
            return (0.0, 1.0)
        cam_prim = stage.GetPrimAtPath(camera_path)
        if not cam_prim or not cam_prim.IsValid():
            return (0.0, 1.0)
        xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        m = xform_cache.GetLocalToWorldTransform(cam_prim)
        fwd_x = -m[2][0]
        fwd_z = -m[2][2]
        length = math.sqrt(fwd_x * fwd_x + fwd_z * fwd_z)
        if length < 1e-6:
            return (0.0, 1.0)
        return (fwd_x / length, fwd_z / length)
    except Exception:
        return (0.0, 1.0)
