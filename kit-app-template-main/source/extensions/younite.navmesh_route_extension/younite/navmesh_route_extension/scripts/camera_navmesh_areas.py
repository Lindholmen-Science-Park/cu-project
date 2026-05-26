"""
Camera NavMesh Areas — Phase 1: Debug Meshes

Discovers fixed cameras (UsdGeom.Camera) under /World, shoots an 11×11
frustum ray grid per camera.  Floor and wall hits are collected; ceiling
hits and misses are discarded.  An outlier filter removes stray rays
(e.g. through small windows), then the 2D convex hull of the remaining
XZ points becomes a flat coloured polygon on the navigation sublayer,
sitting just above the ground (like cctv1_area).  With NavMeshAreaAPI
the baker treats them as named areas (cost modifiers), not obstacles.

NOTE: Meshes MUST live on the navigation sublayer (same as cctv1_area)
because the NavMesh baker only reads prims from the root layer stack.
"""

from typing import Dict, List, Optional, Tuple

import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

_NAV_LAYER_FILENAME = "navigation_layer.usda"

# ── Constants ──────────────────────────────────────────────────────────────────

CAMERA_AREAS_ROOT = "/World/NavmeshCameraAreas"
GROUND_OFFSET = 0.5  # flat polygon sits this many cm above ground
MAX_RAY_DISTANCE = 1500.0  # 15 m — keeps footprint indoors
MIN_GROUND_NORMAL_Y = 0.5

_CAMERA_COLORS: List[Tuple[Tuple[float, float, float], float]] = [
    ((0.9, 0.15, 0.15), 1.6),   # red
    ((0.15, 0.55, 0.9), 1.6),   # blue
    ((0.15, 0.85, 0.25), 1.6),  # green
    ((0.85, 0.65, 0.1), 1.6),   # amber/orange
    ((0.7, 0.2, 0.85), 1.6),    # purple
    ((0.1, 0.8, 0.8), 1.6),     # cyan
]

_U_STEPS = [i / 5.0 for i in range(-5, 6)]             # -1.0 … 1.0  (11)
_V_STEPS = [-0.9 + i * 1.9 / 10.0 for i in range(11)]  # -0.9 … 1.0  (11)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _find_nav_layer(stage) -> Optional[Sdf.Layer]:
    """Find the navigation sublayer in the root layer stack (where cctv1_area lives)."""
    root_layer = stage.GetRootLayer()
    for sub_path in root_layer.subLayerPaths:
        if _NAV_LAYER_FILENAME in sub_path:
            layer = Sdf.Layer.FindRelativeToLayer(root_layer, sub_path)
            if layer:
                return layer
    return None


def _get_edit_layer(stage) -> Sdf.Layer:
    """Return the best layer for writing camera area prims.
    Prefers the navigation sublayer; falls back to root layer."""
    return _find_nav_layer(stage) or stage.GetRootLayer()


def _get_physx_sqi():
    try:
        import omni.physx
        return omni.physx.get_physx_scene_query_interface()
    except Exception:
        return None


def _parse_vec3(raw) -> Optional[Gf.Vec3d]:
    if raw is None:
        return None
    try:
        if isinstance(raw, (list, tuple)) and len(raw) >= 3:
            return Gf.Vec3d(float(raw[0]), float(raw[1]), float(raw[2]))
        if hasattr(raw, "__getitem__"):
            return Gf.Vec3d(float(raw[0]), float(raw[1]), float(raw[2]))
    except Exception:
        pass
    return None


def _raycast(sqi, origin, direction, max_dist):
    import carb._carb as _carb_c
    o = _carb_c.Float3(float(origin[0]), float(origin[1]), float(origin[2]))
    d = _carb_c.Float3(float(direction[0]), float(direction[1]), float(direction[2]))
    result = sqi.raycast_closest(o, d, float(max_dist), bool(True))
    if not result or not result.get("hit", False):
        return None
    pos = _parse_vec3(result.get("position"))
    if pos is None:
        return None
    normal = _parse_vec3(result.get("normal")) or Gf.Vec3d(0, 1, 0)
    return (pos, normal)


def _discover_cameras(stage) -> List[str]:
    world = stage.GetPrimAtPath("/World")
    if not world or not world.IsValid():
        return []
    return [str(c.GetPath()) for c in world.GetChildren() if c.IsA(UsdGeom.Camera)]


def _find_ground_y(sqi, cam_pos: Gf.Vec3d) -> Optional[float]:
    result = _raycast(sqi, cam_pos, Gf.Vec3d(0, -1, 0), 10000.0)
    return result[0][1] if result else None


# ── Outlier filter & convex hull ──────────────────────────────────────────────


def _filter_outliers(
    points: List[Tuple[float, float]],
    cam_xz: Tuple[float, float],
    forward_xz: Tuple[float, float],
    factor: float = 5.0,
) -> List[Tuple[float, float]]:
    """
    Reject points by LATERAL distance from the camera's forward axis.
    Points far down the corridor (forward) are fine; points escaping
    sideways through windows/holes are outliers.
    """
    if len(points) < 5:
        return points

    fx, fz = forward_xz
    cx, cz = cam_xz

    lat_dists: List[float] = []
    for px, pz in points:
        dx, dz = px - cx, pz - cz
        lat = abs(dx * (-fz) + dz * fx)  # perpendicular to forward
        lat_dists.append(lat)

    med_lat = sorted(lat_dists)[len(lat_dists) // 2]
    threshold = max(med_lat * factor, 200.0)

    kept = [p for p, d in zip(points, lat_dists) if d <= threshold]
    return kept if len(kept) >= 3 else points


def _cross_2d(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _convex_hull_2d(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts
    lower = []
    for p in pts:
        while len(lower) >= 2 and _cross_2d(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross_2d(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# ── USD helpers ───────────────────────────────────────────────────────────────


def _ensure_debug_material(stage, layer, cam_name, color_index):
    mat_path = f"{CAMERA_AREAS_ROOT}/Material_{cam_name}"
    prim = stage.GetPrimAtPath(mat_path)
    if prim and prim.IsValid():
        mat = UsdShade.Material(prim)
        if mat:
            return mat

    diffuse, emul = _CAMERA_COLORS[color_index % len(_CAMERA_COLORS)]
    with Usd.EditContext(stage, layer):
        mat = UsdShade.Material.Define(stage, mat_path)
        shader = UsdShade.Shader.Define(stage, f"{mat_path}/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(diffuse[0], diffuse[1], diffuse[2]))
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(diffuse[0] * emul, diffuse[1] * emul, diffuse[2] * emul))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.45)
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _create_footprint_mesh(stage, layer, prim_path, hull_xz, ground_y, material, area_name: str = ""):
    """Create a flat triangulated polygon (fan from centroid) matching the
    cctv1_area pattern so the NavMesh baker treats it as a named area."""
    n = len(hull_xz)
    if n < 3:
        return
    y = ground_y + GROUND_OFFSET

    # Centroid as the fan hub (last point, like cctv1_area)
    cx = sum(x for x, _ in hull_xz) / n
    cz = sum(z for _, z in hull_xz) / n
    points = [Gf.Vec3f(float(x), float(y), float(z)) for x, z in hull_xz]
    points.append(Gf.Vec3f(float(cx), float(y), float(cz)))
    center_idx = n

    # Triangle fan: one tri per edge, all sharing the centroid
    fc: List[int] = []
    fi: List[int] = []
    for i in range(n):
        j = (i + 1) % n
        fc.append(3)
        fi.extend([i, center_idx, j])

    num_face_verts = len(fi)
    normals = [Gf.Vec3f(0, 1, 0)] * num_face_verts

    with Usd.EditContext(stage, layer):
        existing = stage.GetPrimAtPath(prim_path)
        if existing and existing.IsValid():
            stage.RemovePrim(prim_path)
        prim = stage.DefinePrim(prim_path, "Mesh")
        mesh = UsdGeom.Mesh(prim)
        mesh.CreatePointsAttr().Set(points)
        mesh.CreateFaceVertexCountsAttr().Set(fc)
        mesh.CreateFaceVertexIndicesAttr().Set(fi)
        mesh.CreateNormalsAttr().Set(normals)
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
        mesh.CreateDoubleSidedAttr().Set(True)
        mesh.CreateSubdivisionSchemeAttr().Set("none")
        UsdShade.MaterialBindingAPI.Apply(prim)
        UsdShade.MaterialBindingAPI(prim).Bind(material)

        schemas = Sdf.TokenListOp()
        schemas.prependedItems = ["MaterialBindingAPI", "NavMeshAreaAPI"]
        prim.SetMetadata("apiSchemas", schemas)
        if area_name:
            prim.CreateAttribute("nav:area", Sdf.ValueTypeNames.String).Set(area_name)


# ── Public API ─────────────────────────────────────────────────────────────────


def ensure_camera_area_cubes() -> List[str]:
    """Frustum-scan all cameras, build convex-hull guide meshes on root layer."""
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        print("[camera_areas] No stage available"); return []

    sqi = _get_physx_sqi()
    if not sqi:
        print("[camera_areas] PhysX not available"); return []

    cameras = _discover_cameras(stage)
    if not cameras:
        print("[camera_areas] No cameras under /World"); return []

    edit_layer = _get_edit_layer(stage)
    with Usd.EditContext(stage, edit_layer):
        root = stage.GetPrimAtPath(CAMERA_AREAS_ROOT)
        if not root or not root.IsValid():
            stage.DefinePrim(CAMERA_AREAS_ROOT, "Xform")

    created: List[str] = []
    for cam_idx, cam_path in enumerate(cameras):
        cam_name = cam_path.rsplit("/", 1)[-1]

        prim = stage.GetPrimAtPath(cam_path)
        xformable = UsdGeom.Xformable(prim)
        world_mtx = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        cam_pos = Gf.Vec3d(world_mtx.ExtractTranslation())

        focal = prim.GetAttribute("focalLength").Get() or 50.0
        h_ap = prim.GetAttribute("horizontalAperture").Get() or 20.955
        v_ap = prim.GetAttribute("verticalAperture").Get() or 15.2908
        half_h = float(h_ap) / (2.0 * float(focal))
        half_v = float(v_ap) / (2.0 * float(focal))

        rot_mtx = Gf.Matrix4d(world_mtx)
        rot_mtx.SetRow(3, Gf.Vec4d(0, 0, 0, 1))

        fwd_world = rot_mtx.TransformDir(Gf.Vec3d(0, 0, -1))
        fwd_len = (fwd_world[0] ** 2 + fwd_world[2] ** 2) ** 0.5
        if fwd_len < 0.001:
            print(f"[camera_areas] {cam_name} points straight up/down"); continue
        forward_xz = (fwd_world[0] / fwd_len, fwd_world[2] / fwd_len)
        cam_xz = (cam_pos[0], cam_pos[2])

        all_xz: List[Tuple[float, float]] = []
        floor_ys: List[float] = []
        stats = {"floor": 0, "wall": 0, "ceiling": 0, "miss": 0}

        for v in _V_STEPS:
            for u in _U_STEPS:
                local_dir = Gf.Vec3d(u * half_h, v * half_v, -1.0).GetNormalized()
                world_dir = rot_mtx.TransformDir(local_dir).GetNormalized()

                result = _raycast(sqi, cam_pos, world_dir, MAX_RAY_DISTANCE)
                if result is not None:
                    pos, normal = result
                    if normal[1] <= -MIN_GROUND_NORMAL_Y:
                        stats["ceiling"] += 1
                    else:
                        all_xz.append((float(pos[0]), float(pos[2])))
                        if normal[1] >= MIN_GROUND_NORMAL_Y:
                            stats["floor"] += 1
                            floor_ys.append(float(pos[1]))
                        else:
                            stats["wall"] += 1
                else:
                    stats["miss"] += 1

        if len(all_xz) < 3:
            print(f"[camera_areas] Too few points for {cam_name}  {stats}"); continue

        if floor_ys:
            ground_y = sorted(floor_ys)[len(floor_ys) // 2]
        else:
            ground_y = _find_ground_y(sqi, cam_pos)
            if ground_y is None:
                print(f"[camera_areas] No ground for {cam_name}"); continue

        cleaned = _filter_outliers(all_xz, cam_xz, forward_xz)
        hull = _convex_hull_2d(cleaned)

        if len(hull) < 3:
            print(f"[camera_areas] Degenerate hull for {cam_name}"); continue

        area = _area_name(cam_name)
        material = _ensure_debug_material(stage, edit_layer, cam_name, cam_idx)
        _create_footprint_mesh(
            stage, edit_layer,
            f"{CAMERA_AREAS_ROOT}/{cam_name}", hull, ground_y, material,
            area_name=area)

        created.append(cam_name)

    if created:
        print(f"[camera_areas] Created {len(created)} camera areas")

    return created


def _root_has_mesh_children(stage, root) -> bool:
    """Return True only if the root prim has actual Mesh children (not a stale spec)."""
    if not root or not root.IsValid():
        return False
    for child in root.GetChildren():
        if child.IsA(UsdGeom.Mesh):
            return True
    return False


def set_camera_area_cubes_visible(visible: bool) -> None:
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return
    root = stage.GetPrimAtPath(CAMERA_AREAS_ROOT)
    has_meshes = _root_has_mesh_children(stage, root)
    if not has_meshes:
        if visible:
            ensure_camera_area_cubes()
            root = stage.GetPrimAtPath(CAMERA_AREAS_ROOT)
            if not root or not root.IsValid():
                return
        else:
            return
    from younite.payload_orchestrator_core_extension import show_hide, Priority
    if not show_hide(CAMERA_AREAS_ROOT, visible, Priority.MEDIUM, source="camera_areas"):
        imageable = UsdGeom.Imageable(root)
        if imageable:
            if visible:
                imageable.MakeVisible()
            else:
                imageable.MakeInvisible()


# ── NavMesh integration ──────────────────────────────────────────────────────


def _area_name(cam_name: str) -> str:
    return f"{cam_name}_area"


def get_camera_area_names() -> Dict[str, str]:
    """Return {camera_prim_name: navmesh_area_name} for all discovered cameras."""
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return {}
    return {
        p.rsplit("/", 1)[-1]: _area_name(p.rsplit("/", 1)[-1])
        for p in _discover_cameras(stage)
    }


def apply_navmesh_api_to_areas() -> List[str]:
    """Ensure camera area meshes exist (with NavMeshAreaAPI already baked in).
    Returns list of area names."""
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return []

    root = stage.GetPrimAtPath(CAMERA_AREAS_ROOT)
    if not _root_has_mesh_children(stage, root):
        ensure_camera_area_cubes()
        root = stage.GetPrimAtPath(CAMERA_AREAS_ROOT)
        if not root or not root.IsValid():
            return []

    applied: List[str] = []
    for child in root.GetChildren():
        if child.IsA(UsdGeom.Mesh):
            applied.append(_area_name(child.GetName()))

    return applied


def remove_navmesh_api_from_areas() -> List[str]:
    """Remove camera area mesh prims (area defs stay in scene permanently)."""
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return []
    names = list(get_camera_area_names().values())
    root = stage.GetPrimAtPath(CAMERA_AREAS_ROOT)
    if root and root.IsValid():
        edit_layer = _get_edit_layer(stage)
        with Usd.EditContext(stage, edit_layer):
            stage.RemovePrim(CAMERA_AREAS_ROOT)
        # Clean up stale prim specs on the root layer left by MakeInvisible()
        # so future "show" requests correctly detect the areas are gone.
        root_layer = stage.GetRootLayer()
        if root_layer and root_layer != edit_layer:
            stale_spec = root_layer.GetPrimAtPath(CAMERA_AREAS_ROOT)
            if stale_spec:
                parent_spec = stale_spec.nameParent
                if parent_spec:
                    del parent_spec.nameChildren[stale_spec.name]
    return names


