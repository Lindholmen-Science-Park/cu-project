"""Route end marker — cached ``flag.usd`` geometry and session-layer authoring."""

from __future__ import annotations

import contextlib
import functools
import math
import os
from typing import List, Optional, Sequence, Tuple

import carb

from .constants import (
    FLAG_FALLBACK_PREVIEW_DIFFUSE,
    FLAG_ROUTE_END_OFFSET_CM,
    FLAG_ROUTE_END_ROT_X_DEG,
    FLAG_ROUTE_END_TARGET_HEIGHT_CM,
    FLAG_ROUTE_END_TOP_ABOVE_ANCHOR_CM,
    FLAG_ROUTE_END_YAW_OFFSET_DEG,
    ROUTE_END_BEACON_PRIM,
    ROUTE_END_FLAG_BAKED_PRIM_LEGACY,
    ROUTE_END_FLAG_PLACEHOLDER_PRIM,
    ROUTE_END_FLAG_PRIM,
    ROUTE_FLAG_FILENAMES,
    ROUTE_FLAG_MAT,
    SPHERE_RADIUS,
    _FLAG_ASSET_PRIM,
)


class _FlagMeshGeom:
    __slots__ = ("name", "points", "face_vertex_counts", "face_vertex_indices")

    def __init__(self, name, points, face_vertex_counts, face_vertex_indices):
        self.name = name
        self.points = points
        self.face_vertex_counts = face_vertex_counts
        self.face_vertex_indices = face_vertex_indices


_ROUTE_FLAG_DATA_ROOT: Optional[str] = None
_ROUTE_FLAG_GEOMETRY: List[_FlagMeshGeom] = []
_ROUTE_FLAG_NATIVE_HEIGHT_CM: float = 0.0


def _load_route_flag_geometry(asset_path: str) -> Tuple[List[_FlagMeshGeom], float]:
    from pxr import Gf, Usd, UsdGeom, Vt

    meshes: List[_FlagMeshGeom] = []
    native_h = 0.0
    try:
        st = Usd.Stage.Open(asset_path)
        if not st:
            return [], 0.0

        root = st.GetDefaultPrim()
        if not root or not root.IsValid():
            root = st.GetPrimAtPath(_FLAG_ASSET_PRIM)
        if not root or not root.IsValid():
            return [], 0.0

        try:
            img = UsdGeom.Imageable(root)
            if img:
                bbox = img.ComputeWorldBound(Usd.TimeCode.Default(), UsdGeom.Tokens.default_)
                rng = bbox.ComputeAlignedRange()
                native_h = float(rng.GetMax()[1] - rng.GetMin()[1])
        except Exception:
            native_h = 0.0

        tc = Usd.TimeCode.Default()
        idx = 0
        for prim in Usd.PrimRange(root):
            if not prim.IsA(UsdGeom.Mesh):
                continue
            geom = UsdGeom.Mesh(prim)
            pts_attr = geom.GetPointsAttr()
            fvc_attr = geom.GetFaceVertexCountsAttr()
            fvi_attr = geom.GetFaceVertexIndicesAttr()
            if not pts_attr or not fvc_attr or not fvi_attr:
                continue
            pts = pts_attr.Get(tc)
            fvc = fvc_attr.Get(tc)
            fvi = fvi_attr.Get(tc)
            if not pts or not fvc or not fvi:
                continue

            mat = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(tc)
            transformed: List = []
            for p in pts:
                wp = mat.Transform(Gf.Vec3d(float(p[0]), float(p[1]), float(p[2])))
                transformed.append(Gf.Vec3f(float(wp[0]), float(wp[1]), float(wp[2])))

            meshes.append(
                _FlagMeshGeom(
                    name=f"mesh_{idx:02d}",
                    points=Vt.Vec3fArray(transformed),
                    face_vertex_counts=Vt.IntArray(list(fvc)),
                    face_vertex_indices=Vt.IntArray(list(fvi)),
                )
            )
            idx += 1
    except Exception as e:
        carb.log_warn(f"[navmesh_route] route_end_flag: failed to read {asset_path}: {e}")
        return [], 0.0

    if native_h <= 1e-6:
        native_h = 600.0
    return meshes, native_h


def set_route_flag_data_root(data_dir: Optional[str]) -> None:
    """Wire ``source/data`` and pre-bake flag mesh geometry into the module cache."""
    global _ROUTE_FLAG_DATA_ROOT, _ROUTE_FLAG_GEOMETRY, _ROUTE_FLAG_NATIVE_HEIGHT_CM
    _ROUTE_FLAG_DATA_ROOT = (data_dir or "").strip() or None
    try:
        _resolve_route_flag_asset_path_fallback.cache_clear()
    except Exception:
        pass
    _ROUTE_FLAG_GEOMETRY = []
    _ROUTE_FLAG_NATIVE_HEIGHT_CM = 0.0

    p = _resolve_route_flag_asset_path()
    if not p:
        print("[navmesh_route] Route end flag asset NOT FOUND under source/data/Assets/Flag/flag.usd (or .usdc)")
        return

    meshes, native_h = _load_route_flag_geometry(p)
    _ROUTE_FLAG_GEOMETRY = meshes
    _ROUTE_FLAG_NATIVE_HEIGHT_CM = native_h
    if meshes:
        print(
            f"[navmesh_route] Route end flag asset: {p} "
            f"({len(meshes)} mesh(es), native height {native_h:.1f} cm)"
        )
    else:
        print(f"[navmesh_route] Route end flag asset {p} contains no meshes — using placeholder sphere fallback")


def _usd_asset_path_fs(p: str) -> str:
    return os.path.normpath(p).replace("\\", "/")


def _resolve_route_flag_asset_path() -> Optional[str]:
    dr = _ROUTE_FLAG_DATA_ROOT
    if dr:
        base = os.path.normpath(os.path.join(dr, "Assets", "Flag"))
        for fn in ROUTE_FLAG_FILENAMES:
            p = os.path.join(base, fn)
            if os.path.isfile(p):
                return _usd_asset_path_fs(p)
    return _resolve_route_flag_asset_path_fallback()


def _find_flag_asset_under_probe(probe) -> Optional[str]:
    from pathlib import Path

    rel_names = [Path("Assets") / "Flag" / fn for fn in ROUTE_FLAG_FILENAMES]
    for rel in rel_names:
        if probe.name.lower() == "source" and (probe / "data" / rel).is_file():
            return _usd_asset_path_fs(str((probe / "data" / rel).resolve()))
        if probe.name.lower() == "kit-app-template-main" and (probe / "source" / "data" / rel).is_file():
            return _usd_asset_path_fs(str((probe / "source" / "data" / rel).resolve()))
        for sub in ("data",):
            c = probe / sub
            p = c / rel
            if c.is_dir() and p.is_file():
                return _usd_asset_path_fs(str(p.resolve()))
        c2 = probe / "source" / "data"
        p2 = c2 / rel
        if c2.is_dir() and p2.is_file():
            return _usd_asset_path_fs(str(p2.resolve()))
    return None


@functools.lru_cache(maxsize=1)
def _resolve_route_flag_asset_path_fallback() -> Optional[str]:
    from pathlib import Path

    # Legacy ``navmesh_shortest_path.py`` lived in ``scripts/``; probe from there so
    # packaged fallback matches monolithic discovery (repo / cwd / dev layouts).
    scripts_dir = Path(__file__).resolve().parent.parent
    probe = scripts_dir
    for _ in range(12):
        hit = _find_flag_asset_under_probe(probe)
        if hit:
            return hit
        if probe.parent == probe:
            break
        probe = probe.parent

    here = scripts_dir
    for fn in ROUTE_FLAG_FILENAMES:
        rel = Path("Assets") / "Flag" / fn
        cwd_candidate = Path(os.getcwd()) / "source" / "data" / rel
        if cwd_candidate.is_file():
            return _usd_asset_path_fs(str(cwd_candidate.resolve()))

    for fn in ROUTE_FLAG_FILENAMES:
        rel = Path("Assets") / "Flag" / fn
        dev_guess = (here / ".." / ".." / ".." / ".." / ".." / "data" / rel).resolve()
        if dev_guess.is_file():
            return _usd_asset_path_fs(str(dev_guess))

    return None


def _route_flag_yaw_deg_toward(ax: float, az: float, bx: float, bz: float) -> float:
    dx = bx - ax
    dz = bz - az
    if dx * dx + dz * dz < 1e-8:
        return 0.0
    return math.degrees(math.atan2(dx, dz))


def _world_pos_before_path_end(points: List, offset_cm: float):
    from pxr import Gf

    if not points:
        return None
    if len(points) < 2:
        return Gf.Vec3f(points[0])
    if offset_cm <= 0.0:
        return Gf.Vec3f(points[-1])

    remaining = float(offset_cm)
    cur_idx = len(points) - 1
    while cur_idx > 0:
        a = points[cur_idx - 1]
        b = points[cur_idx]
        vx = float(b[0] - a[0])
        vy = float(b[1] - a[1])
        vz = float(b[2] - a[2])
        seg_len = math.sqrt(vx * vx + vy * vy + vz * vz)
        if seg_len < 1e-8:
            cur_idx -= 1
            continue
        if remaining <= seg_len:
            nx = float(b[0]) - (vx / seg_len) * remaining
            ny = float(b[1]) - (vy / seg_len) * remaining
            nz = float(b[2]) - (vz / seg_len) * remaining
            return Gf.Vec3f(nx, ny, nz)
        remaining -= seg_len
        cur_idx -= 1

    return Gf.Vec3f(float(points[0][0]), float(points[0][1]), float(points[0][2]))


def _remove_route_flag_placeholder(stage, group_path: str) -> None:
    pth = f"{group_path}/{ROUTE_END_FLAG_PLACEHOLDER_PRIM}"
    prim = stage.GetPrimAtPath(pth)
    if prim and prim.IsValid():
        stage.RemovePrim(pth)


def _remove_route_end_beacon(stage, group_path: str) -> None:
    pth = f"{group_path}/{ROUTE_END_BEACON_PRIM}"
    prim = stage.GetPrimAtPath(pth)
    if prim and prim.IsValid():
        stage.RemovePrim(pth)


def _remove_route_flag_baked(stage, group_path: str) -> None:
    pth = f"{group_path}/{ROUTE_END_FLAG_BAKED_PRIM_LEGACY}"
    prim = stage.GetPrimAtPath(pth)
    if prim and prim.IsValid():
        stage.RemovePrim(pth)


def _remove_route_end_flag(stage, group_path: str) -> None:
    _remove_route_flag_placeholder(stage, group_path)
    _remove_route_flag_baked(stage, group_path)
    _remove_route_end_beacon(stage, group_path)
    flag_path = f"{group_path}/{ROUTE_END_FLAG_PRIM}"
    prim = stage.GetPrimAtPath(flag_path)
    if prim and prim.IsValid():
        stage.RemovePrim(flag_path)


def _ensure_route_flag_fallback_material(stage, mat_path: str):
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    prim = stage.GetPrimAtPath(mat_path)
    if prim and prim.IsValid():
        mat = UsdShade.Material(prim)
        if not mat:
            mat = UsdShade.Material.Define(stage, mat_path)
    else:
        mat = UsdShade.Material.Define(stage, mat_path)

    shader_path = f"{mat_path}/Shader"
    sh_prim = stage.GetPrimAtPath(shader_path)
    if sh_prim and sh_prim.IsValid():
        shader = UsdShade.Shader(sh_prim)
    else:
        shader = UsdShade.Shader.Define(stage, shader_path)
    shader.CreateIdAttr("UsdPreviewSurface")

    c = Gf.Vec3f(
        float(FLAG_FALLBACK_PREVIEW_DIFFUSE[0]),
        float(FLAG_FALLBACK_PREVIEW_DIFFUSE[1]),
        float(FLAG_FALLBACK_PREVIEW_DIFFUSE[2]),
    )
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(c)
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.0, 0.0, 0.0))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.55)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _author_route_flag_usd_reference(
    stage,
    flag_path: str,
    tx: float,
    ty: float,
    tz: float,
    yaw_deg: float,
    uniform_scale: float,
    asset_fs_path: str,
) -> bool:
    from pxr import Gf, Sdf, Usd, UsdGeom

    session = stage.GetSessionLayer()
    ctx = Usd.EditContext(stage, session) if session else contextlib.nullcontext()
    ap = _usd_asset_path_fs(asset_fs_path)
    try:
        with ctx:
            prim0 = stage.GetPrimAtPath(flag_path)
            if prim0 and prim0.IsValid():
                stage.RemovePrim(flag_path)
            prim = stage.DefinePrim(flag_path, "Xform")
            xform = UsdGeom.Xformable(prim)
            xform.ClearXformOpOrder()
            xform.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))
            xform.AddRotateXYZOp().Set(Gf.Vec3f(float(FLAG_ROUTE_END_ROT_X_DEG), float(yaw_deg), 0.0))
            xform.AddScaleOp().Set(Gf.Vec3f(uniform_scale, uniform_scale, uniform_scale))
            prim.GetReferences().AddReference(Sdf.Reference(ap, Sdf.Path("/World")))
        return True
    except Exception as e:
        carb.log_warn(f"[navmesh_route] route_end_flag: flag.usd reference failed: {e}")
        return False


def _ensure_route_flag_placeholder_sphere(
    stage,
    group_path: str,
    center: Tuple[float, float, float],
) -> None:
    from pxr import Gf, UsdGeom, UsdShade

    _remove_route_flag_placeholder(stage, group_path)
    path = f"{group_path}/{ROUTE_END_FLAG_PLACEHOLDER_PRIM}"
    prim = stage.DefinePrim(path, "Sphere")
    UsdGeom.Sphere(prim).CreateRadiusAttr().Set(max(float(SPHERE_RADIUS) * 3.5, 28.0))
    xf = UsdGeom.Xformable(prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(center[0], center[1], center[2]))
    mat = _ensure_route_flag_fallback_material(stage, f"{group_path}/{ROUTE_FLAG_MAT}")
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)


def _author_route_flag_from_cache(
    stage,
    flag_path: str,
    mat_path: str,
    tx: float,
    ty: float,
    tz: float,
    yaw_deg: float,
    uniform_scale: float,
) -> int:
    from pxr import Gf, Usd, UsdGeom, UsdShade

    if not _ROUTE_FLAG_GEOMETRY:
        return 0

    session = stage.GetSessionLayer()
    ctx = Usd.EditContext(stage, session) if session else contextlib.nullcontext()
    mat = _ensure_route_flag_fallback_material(stage, mat_path)

    authored = 0
    try:
        with ctx:
            prim = stage.GetPrimAtPath(flag_path)
            if prim and prim.IsValid():
                stage.RemovePrim(flag_path)
            prim = stage.DefinePrim(flag_path, "Xform")

            xform = UsdGeom.Xformable(prim)
            xform.ClearXformOpOrder()
            xform.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))
            xform.AddRotateXYZOp().Set(Gf.Vec3f(float(FLAG_ROUTE_END_ROT_X_DEG), float(yaw_deg), 0.0))
            xform.AddScaleOp().Set(Gf.Vec3f(uniform_scale, uniform_scale, uniform_scale))

            for geom in _ROUTE_FLAG_GEOMETRY:
                dst = f"{flag_path}/{geom.name}"
                mprim = stage.DefinePrim(dst, "Mesh")
                mesh = UsdGeom.Mesh(mprim)
                mesh.CreatePointsAttr(geom.points)
                mesh.CreateFaceVertexCountsAttr(geom.face_vertex_counts)
                mesh.CreateFaceVertexIndicesAttr(geom.face_vertex_indices)
                try:
                    mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
                except Exception:
                    pass
                try:
                    mesh.CreateDoubleSidedAttr(True)
                except Exception:
                    pass
                UsdShade.MaterialBindingAPI.Apply(mprim).Bind(mat)
                authored += 1
    except Exception as e:
        carb.log_warn(f"[navmesh_route] route_end_flag author failed: {e}")
        return 0

    return authored


def update_route_end_flag(stage, group_path: str, path_polyline: Sequence) -> bool:
    """Place ``flag.usd`` (reference) near the path end; mesh preview only if reference fails."""
    flag_path = f"{group_path}/{ROUTE_END_FLAG_PRIM}"
    if len(path_polyline) < 2:
        _remove_route_end_flag(stage, group_path)
        return True

    anchor = _world_pos_before_path_end(list(path_polyline), FLAG_ROUTE_END_OFFSET_CM)
    if anchor is None:
        _remove_route_end_flag(stage, group_path)
        return True

    dest = path_polyline[-1]
    yaw = _route_flag_yaw_deg_toward(
        float(anchor[0]),
        float(anchor[2]),
        float(dest[0]),
        float(dest[2]),
    ) + float(FLAG_ROUTE_END_YAW_OFFSET_DEG)
    tx = float(anchor[0])
    ty = float(anchor[1]) + float(FLAG_ROUTE_END_TOP_ABOVE_ANCHOR_CM) - float(
        FLAG_ROUTE_END_TARGET_HEIGHT_CM
    )
    tz = float(anchor[2])

    mat_path = f"{group_path}/{ROUTE_FLAG_MAT}"

    _remove_route_flag_baked(stage, group_path)
    _remove_route_end_beacon(stage, group_path)

    nh = float(_ROUTE_FLAG_NATIVE_HEIGHT_CM)
    den = nh if nh > 1e-6 else 600.0
    uniform = float(FLAG_ROUTE_END_TARGET_HEIGHT_CM) / den

    ap = _resolve_route_flag_asset_path()
    if ap and _author_route_flag_usd_reference(
        stage, flag_path, tx, ty, tz, yaw, uniform, ap,
    ):
        _remove_route_flag_placeholder(stage, group_path)
        return True

    if _ROUTE_FLAG_GEOMETRY and nh > 1e-6:
        uniform_m = float(FLAG_ROUTE_END_TARGET_HEIGHT_CM) / nh
        authored = _author_route_flag_from_cache(
            stage, flag_path, mat_path, tx, ty, tz, yaw, uniform_m,
        )
        if authored > 0:
            _remove_route_flag_placeholder(stage, group_path)
            return True
        carb.log_warn("[navmesh_route] route_end_flag: cache author returned 0 — falling back to placeholder")

    prim = stage.GetPrimAtPath(flag_path)
    if prim and prim.IsValid():
        stage.RemovePrim(flag_path)
    _ensure_route_flag_placeholder_sphere(stage, group_path, (tx, ty, tz))
    return True
