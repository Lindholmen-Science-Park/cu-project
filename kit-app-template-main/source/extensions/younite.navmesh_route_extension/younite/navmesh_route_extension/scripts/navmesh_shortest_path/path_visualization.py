"""USD visualization — waypoint spheres along a polyline (session layer)."""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import carb
import omni.usd

from .constants import (
    CURVE_WIDTH,
    PATH_PRIM,
    SPHERE_COLOR,
    SPHERE_EMISSIVE_INTENSITY,
    SPHERE_RADIUS,
    SPHERE_SPACING,
    SPHERE_Y_OFFSET,
)
from .navmesh_pathfind import calculate_path_points
from .route_end_flag import update_route_end_flag


def _resample_path(points: List, spacing: float) -> List:
    """Resample a polyline into evenly-spaced points along its length."""
    from pxr import Gf

    if len(points) < 2:
        return list(points)

    result: List = [points[0]]
    leftover = 0.0

    for i in range(1, len(points)):
        p0 = points[i - 1]
        p1 = points[i]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        dz = p1[2] - p0[2]
        seg_len = math.sqrt(dx * dx + dy * dy + dz * dz)

        if seg_len < 1e-6:
            continue

        inv = 1.0 / seg_len
        ux, uy, uz = dx * inv, dy * inv, dz * inv

        d = spacing - leftover
        while d <= seg_len:
            result.append(
                Gf.Vec3f(
                    p0[0] + ux * d,
                    p0[1] + uy * d,
                    p0[2] + uz * d,
                )
            )
            d += spacing

        leftover = seg_len - (d - spacing)

    last = points[-1]
    if len(result) > 0:
        prev = result[-1]
        gap = math.sqrt(
            (last[0] - prev[0]) ** 2 + (last[1] - prev[1]) ** 2 + (last[2] - prev[2]) ** 2
        )
        if gap > 1e-3:
            result.append(last)
    else:
        result.append(last)

    return result


def _ensure_route_path_hierarchy(stage, group_path: str) -> None:
    if not group_path or not str(group_path).startswith("/"):
        return
    segments = [s for s in str(group_path).strip("/").split("/") if s]
    if len(segments) < 2:
        return
    acc = ""
    for seg in segments[:-1]:
        acc = f"{acc}/{seg}" if acc else f"/{seg}"
        pr = stage.GetPrimAtPath(acc)
        if not pr or not pr.IsValid():
            stage.DefinePrim(acc, "Xform")


def _ensure_path_group(stage, group_path: str) -> None:
    from pxr import UsdGeom

    _ensure_route_path_hierarchy(stage, group_path)
    prim = stage.GetPrimAtPath(group_path)
    if prim and prim.IsValid():
        if not UsdGeom.Xform(prim):
            stage.RemovePrim(group_path)
            stage.DefinePrim(group_path, "Xform")
    else:
        stage.DefinePrim(group_path, "Xform")


def _ensure_glow_material(stage, mat_path: str):
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    prim = stage.GetPrimAtPath(mat_path)
    if prim and prim.IsValid():
        mat = UsdShade.Material(prim)
        if mat:
            return mat

    mat = UsdShade.Material.Define(stage, mat_path)

    shader_path = f"{mat_path}/Shader"
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.CreateIdAttr("UsdPreviewSurface")

    color = Gf.Vec3f(SPHERE_COLOR[0], SPHERE_COLOR[1], SPHERE_COLOR[2])
    emissive = Gf.Vec3f(
        color[0] * SPHERE_EMISSIVE_INTENSITY,
        color[1] * SPHERE_EMISSIVE_INTENSITY,
        color[2] * SPHERE_EMISSIVE_INTENSITY,
    )

    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color)
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(emissive)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.85)

    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _place_spheres(
    stage,
    group_path: str,
    positions: List,
    radius: float = SPHERE_RADIUS,
    y_offset: float = SPHERE_Y_OFFSET,
) -> None:
    from pxr import Gf, UsdGeom, UsdShade, Vt

    mat_path = f"{group_path}/GlowMaterial"
    mat = _ensure_glow_material(stage, mat_path)
    needed = len(positions)

    group_prim = stage.GetPrimAtPath(group_path)
    existing: List[str] = []
    if group_prim and group_prim.IsValid():
        for child in group_prim.GetChildren():
            name = child.GetName()
            if name.startswith("wp_"):
                existing.append(str(child.GetPath()))
        existing.sort()

    reuse_count = min(needed, len(existing))
    for i in range(reuse_count):
        prim = stage.GetPrimAtPath(existing[i])
        xform = UsdGeom.Xformable(prim)
        ops = xform.GetOrderedXformOps()
        pos = positions[i]
        new_pos = Gf.Vec3d(float(pos[0]), float(pos[1]) + y_offset, float(pos[2]))
        if ops:
            ops[0].Set(new_pos)
        else:
            xform.ClearXformOpOrder()
            xform.AddTranslateOp().Set(new_pos)

    for i in range(reuse_count, needed):
        sphere_path = f"{group_path}/wp_{i:04d}"
        prim = stage.DefinePrim(sphere_path, "Sphere")
        sphere = UsdGeom.Sphere(prim)
        sphere.CreateRadiusAttr().Set(float(radius))

        xform = UsdGeom.Xformable(prim)
        xform.ClearXformOpOrder()
        pos = positions[i]
        xform.AddTranslateOp().Set(
            Gf.Vec3d(
                float(pos[0]),
                float(pos[1]) + y_offset,
                float(pos[2]),
            )
        )

        UsdShade.MaterialBindingAPI.Apply(prim)
        UsdShade.MaterialBindingAPI(prim).Bind(mat)

        sphere.CreateDisplayColorAttr().Set(
            Vt.Vec3fArray([Gf.Vec3f(SPHERE_COLOR[0], SPHERE_COLOR[1], SPHERE_COLOR[2])])
        )

    for i in range(needed, len(existing)):
        stage.RemovePrim(existing[i])


def remove_path_curve(path_prim: str = PATH_PRIM) -> bool:
    """Remove the path visualization group from the stage."""
    try:
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        if stage is None:
            return False

        prim = stage.GetPrimAtPath(path_prim)
        if prim and prim.IsValid():
            stage.RemovePrim(path_prim)
            return True
        return True
    except Exception as e:
        carb.log_warn(f"[navmesh_route] remove_path_curve({path_prim}): {e}")
        return False


def draw_path_curve(
    points_gf: list,
    path_prim: str = PATH_PRIM,
    curve_width: float = CURVE_WIDTH,
) -> Tuple[bool, Optional[str]]:
    """Draw floating glowing spheres along an already-computed polyline."""
    try:
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        if stage is None:
            return False, "No USD stage loaded. Open a scene first."

        if len(points_gf) < 2:
            return False, f"Need at least 2 path points, got {len(points_gf)}"

        resampled = _resample_path(points_gf, SPHERE_SPACING)
        _ensure_path_group(stage, path_prim)
        update_route_end_flag(stage, path_prim, points_gf)
        _place_spheres(stage, path_prim, list(resampled))
        return True, None
    except Exception as e:
        return False, f"Failed to create path spheres: {e}"


def calculate_path(
    startpoint_path,
    endpoint_path,
    path_prim: str = PATH_PRIM,
    curve_width: float = CURVE_WIDTH,
    verbose: bool = True,
    camera_area_costs=None,
    start_use_ground: bool = True,
):
    """Calculate and visualize shortest path between two points using NavMesh."""
    success, points_gf, error_msg = calculate_path_points(
        startpoint_path,
        endpoint_path,
        start_use_ground=start_use_ground,
        camera_area_costs=camera_area_costs,
    )
    if not success:
        if verbose and error_msg:
            print(
                f"[navmesh_route] path failed: start={startpoint_path!r} "
                f"end={endpoint_path!r} — {error_msg}"
            )
        return False, 0, error_msg

    ok, draw_err = draw_path_curve(points_gf, path_prim=path_prim, curve_width=curve_width)
    if not ok:
        if verbose and draw_err:
            print(
                f"[navmesh_route] path draw failed: start={startpoint_path!r} "
                f"end={endpoint_path!r} prim={path_prim} — {draw_err}"
            )
        return False, 0, draw_err

    count = len(points_gf)
    if verbose:
        print(
            f"[navmesh_route] path ok: start={startpoint_path!r} end={endpoint_path!r} "
            f"prim={path_prim} nav_points={count}"
        )

    return True, count, None


def main():
    CUBE_A = "/World/Cube1"
    CUBE_B = "/World/Cube2"
    success, count, error = calculate_path(CUBE_A, CUBE_B)
    if not success:
        print(f"[navmesh_route] path test failed: {error}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[navmesh_route] path test error: {e}")
        import traceback

        traceback.print_exc()
