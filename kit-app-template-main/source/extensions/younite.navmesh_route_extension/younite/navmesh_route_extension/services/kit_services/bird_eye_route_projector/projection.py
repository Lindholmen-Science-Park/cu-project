"""World-space waypoints → active viewport screen pixels (Kit renderer coords)."""

from __future__ import annotations

from typing import List, Optional

from .resolution import get_renderer_resolution
from .types import Vec3


def project_waypoints_to_screen(source: List[Vec3]) -> Optional[list]:
    from omni.kit.viewport.utility import get_active_viewport
    import omni.usd
    from pxr import Gf, UsdGeom

    viewport_api = get_active_viewport()
    if not viewport_api:
        return None

    wtndc = getattr(viewport_api, "world_to_ndc", None)
    if wtndc is None or not hasattr(wtndc, "Transform"):
        return None

    res = get_renderer_resolution()
    if not res:
        return None
    width, height = res

    usd_context = omni.usd.get_context()
    stage = usd_context.get_stage() if usd_context else None

    camera_inv = None
    try:
        camera_path = getattr(viewport_api, "camera_path", None)
        if camera_path and stage:
            cam_prim = stage.GetPrimAtPath(camera_path)
            if cam_prim and cam_prim.IsValid():
                camera_inv = UsdGeom.Xformable(cam_prim).ComputeLocalToWorldTransform(0).GetInverse()
    except Exception:
        pass

    result = []
    for wp in source:
        pos = Gf.Vec3d(wp[0], wp[1], wp[2])

        if camera_inv:
            cam_pos = camera_inv.Transform(pos)
            if float(cam_pos[2]) >= 0.0:
                continue

        v = wtndc.Transform(pos)
        ndc_x, ndc_y = float(v[0]), float(v[1])
        sx = int((ndc_x + 1.0) * 0.5 * width)
        sy = int((1.0 - ndc_y) * 0.5 * height)
        result.append({"sx": sx, "sy": sy, "wx": wp[0], "wy": wp[1], "wz": wp[2]})

    return result
