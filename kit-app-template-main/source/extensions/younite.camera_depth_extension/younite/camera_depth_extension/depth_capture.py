"""
Depth point-cloud capture via PhysX raycasting.

Shoots one ray per pixel of a virtual pinhole camera grid, uses
omni.physx scene-query raycasts to find hit positions, and writes the
result as a UsdGeom.Points prim.

No renderer pipeline, no viewport switch -- purely physics-based.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
import carb._carb as _carb_c

import omni.usd
import omni.kit.app
import omni.physx

from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt

# Sampling settings
RESOLUTION = (640, 480)
MAX_DISTANCE = 1_500.0  # cm (= 15 m); matches camera coverage MAX_RAY_DISTANCE
POINT_SIZE = 0.25         # visual radius in cm
POINT_COLOR = Gf.Vec3f(1.0, 0.3, 0.0)    # vibrant alert orange

# How many rows to process before yielding back to the event loop
ROWS_PER_YIELD = 60


# ------------------------------------------------------------------
# USD helpers
# ------------------------------------------------------------------

def _get_stage() -> Usd.Stage:
    return omni.usd.get_context().get_stage()


def _ensure_emissive_material(stage: Usd.Stage, mat_path: str) -> UsdShade.Material:
    """Create or reuse a bright emissive material so points glow in any lighting."""
    prim = stage.GetPrimAtPath(mat_path)
    if prim and prim.IsValid():
        mat = UsdShade.Material(prim)
        if mat:
            return mat

    mat = UsdShade.Material.Define(stage, mat_path)
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(POINT_COLOR)
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(POINT_COLOR[0] * 3.0, POINT_COLOR[1] * 3.0, POINT_COLOR[2] * 3.0))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _ensure_points_prim(stage: Usd.Stage, prim_path: str) -> UsdGeom.Points:
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        pts = UsdGeom.Points.Define(stage, prim_path)
    else:
        pts = UsdGeom.Points(prim)

    pts.CreateWidthsAttr().Set(Vt.FloatArray([POINT_SIZE]))
    pts.CreateDisplayColorAttr().Set(Vt.Vec3fArray([POINT_COLOR]))

    mat = _ensure_emissive_material(stage, f"{prim_path}/EmissiveMaterial")
    points_prim = stage.GetPrimAtPath(prim_path)
    UsdShade.MaterialBindingAPI.Apply(points_prim)
    UsdShade.MaterialBindingAPI(points_prim).Bind(mat)

    return pts


def _set_usd_points(points_prim: UsdGeom.Points, xyz_world: np.ndarray):
    points_prim.GetPointsAttr().Set(
        Vt.Vec3fArray([Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in xyz_world])
    )


# ------------------------------------------------------------------
# Camera model (pinhole)
# ------------------------------------------------------------------

def _get_camera_intrinsics(camera_prim: Usd.Prim, width: int, height: int):
    cam = UsdGeom.Camera(camera_prim)
    f = cam.GetFocalLengthAttr().Get() or 24.0
    ha = cam.GetHorizontalApertureAttr().Get() or 20.955
    va = cam.GetVerticalApertureAttr().Get() or 15.2908

    fx = (f / ha) * float(width)
    fy = (f / va) * float(height)
    cx = (width - 1) * 0.5
    cy = (height - 1) * 0.5
    return fx, fy, cx, cy


def _get_camera_world_transform(stage: Usd.Stage, camera_path: str) -> Gf.Matrix4d:
    cache = UsdGeom.XformCache()
    prim = stage.GetPrimAtPath(camera_path)
    return cache.GetLocalToWorldTransform(prim)


# ------------------------------------------------------------------
# Uniform grid raycasting (one ray per pixel)
# ------------------------------------------------------------------

async def _capture_async(camera_prim_path: str, points_prim_path: str) -> int:
    stage = _get_stage()
    cam_prim = stage.GetPrimAtPath(camera_prim_path)
    if not cam_prim or not cam_prim.IsValid():
        raise RuntimeError(f"Camera prim not found: {camera_prim_path}")

    w, h = RESOLUTION
    fx, fy, cx, cy = _get_camera_intrinsics(cam_prim, w, h)
    cam_T_world = _get_camera_world_transform(stage, camera_prim_path)
    cam_origin = cam_T_world.Transform(Gf.Vec3d(0, 0, 0))
    origin_f3 = _carb_c.Float3(float(cam_origin[0]), float(cam_origin[1]), float(cam_origin[2]))

    app = omni.kit.app.get_app()
    sq = omni.physx.get_physx_scene_query_interface()

    print(f"[camera_depth] raycasting from {camera_prim_path} "
          f"({w}x{h} = {w * h} rays, max_dist={MAX_DISTANCE:.0f}cm)")

    points: List[Tuple[float, float, float]] = []

    for row in range(h):
        for col in range(w):
            # Pixel -> camera-space direction
            dx = (col - cx) / fx
            dy = -(row - cy) / fy
            dz = -1.0
            inv_len = 1.0 / (dx * dx + dy * dy + dz * dz) ** 0.5
            dx *= inv_len
            dy *= inv_len
            dz *= inv_len

            # Camera-space -> world-space direction
            p1 = cam_T_world.Transform(Gf.Vec3d(dx, dy, dz))
            wd = p1 - cam_origin
            wd.Normalize()

            dir_f3 = _carb_c.Float3(float(wd[0]), float(wd[1]), float(wd[2]))
            hit = sq.raycast_closest(origin_f3, dir_f3, float(MAX_DISTANCE), bool(True))

            if hit and hit.get("hit", False):
                p = hit.get("position")
                if p is not None:
                    points.append((float(p[0]), float(p[1]), float(p[2])))

        # Yield periodically so the app stays responsive
        if (row + 1) % ROWS_PER_YIELD == 0:
            await app.next_update_async()

    xyz = np.array(points, dtype=np.float32) if points else np.zeros((0, 3), dtype=np.float32)

    print(f"[camera_depth] raycast produced {len(xyz)} points")

    pts_prim = _ensure_points_prim(stage, points_prim_path)
    _set_usd_points(pts_prim, xyz)

    return len(xyz)


def capture_depth_pointcloud(camera_prim_path: str, points_prim_path: str):
    """
    Returns an awaitable coroutine.  The caller (extension.py) schedules it
    with asyncio.ensure_future().
    """
    return _capture_async(camera_prim_path, points_prim_path)
