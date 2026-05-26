"""
Sound NavMesh Areas — fixed-size radial ground-following zones around
sound_location prims.

All areas use FIXED_RADIUS (~5.6 m).  Sliders control NavMesh cost
scoring only (higher cost = harder to walk through), not area size.

Pure horizontal raycasting from the sound source (1.5 m above ground):

1. For each of NUM_H_RAYS angles (360°), cast one horizontal ray.
2. If the ray hits geometry, the boundary for that angle = hit distance.
   The hit point is projected down to ground level (flat polygon).
3. If the ray misses, the boundary extends to FIXED_RADIUS.
4. If no walkable floor exists under a boundary point, binary-search
   inward to find the floor edge (cliff clipping).
5. The result is an ordered polygon (one vertex per angle) that naturally
   represents concave shapes — indents at walls, opens at doorways.
6. All vertices sit at source ground Y + small offset (flat polygon).
7. Triangle-fan mesh from the source XZ as the centroid.
"""

from typing import Dict, List, Optional, Tuple
import math

import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

_NAV_LAYER_FILENAME = "navigation_layer.usda"

SOUND_AREAS_ROOT = "/World/NavmeshSoundAreas"
GROUND_OFFSET = 0.5
RAY_HEIGHT = 150.0         # 1.5 m above ground
NUM_H_RAYS = 72            # 360° / 72 = 5° per step
WALL_INSET = 5.0           # pull boundary 5 cm away from wall face
MIN_BOUNDARY = 20.0        # minimum boundary distance per ray (cm)
FIXED_RADIUS = 557.5       # cm — preset size for all sound areas (≈ 5.6 m)
GROUND_PROBE_OFFSET = 300.0  # probe ground from 3 m above xform
FLOOR_TOLERANCE = 30.0       # cm — max gap between polygon and actual floor below
MIN_FLOOR_NORMAL_Y = 0.7    # surface must face upward to count as "floor"
CLIFF_SEARCH_STEPS = 6       # binary-search iterations for floor edge

_SOUND_COLORS: List[Tuple[Tuple[float, float, float], float]] = [
    ((0.85, 0.55, 0.1), 1.4),   # amber
    ((0.1, 0.65, 0.85), 1.4),   # teal
    ((0.75, 0.2, 0.75), 1.4),   # purple
    ((0.2, 0.8, 0.4), 1.4),     # green
    ((0.9, 0.3, 0.3), 1.4),     # red
    ((0.3, 0.4, 0.9), 1.4),     # blue
]

# ── Low-level helpers ──────────────────────────────────────────────────────────


def _find_nav_layer(stage) -> Optional[Sdf.Layer]:
    root_layer = stage.GetRootLayer()
    for sub_path in root_layer.subLayerPaths:
        if _NAV_LAYER_FILENAME in sub_path:
            layer = Sdf.Layer.FindRelativeToLayer(root_layer, sub_path)
            if layer:
                return layer
    return None


def _get_edit_layer(stage) -> Sdf.Layer:
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
    result = sqi.raycast_closest(o, d, float(max_dist), True)
    if not result or not result.get("hit", False):
        return None
    pos = _parse_vec3(result.get("position"))
    if pos is None:
        return None
    normal = _parse_vec3(result.get("normal")) or Gf.Vec3d(0, 1, 0)
    return (pos, normal)


def _find_ground_y(sqi, pos: Gf.Vec3d) -> Optional[float]:
    """Probe downward from well above the xform to reliably find the floor.
    Starting from the xform itself can fail if it sits exactly at the mesh surface."""
    probe_y = float(pos[1]) + GROUND_PROBE_OFFSET
    probe_origin = Gf.Vec3d(float(pos[0]), probe_y, float(pos[2]))
    max_probe = GROUND_PROBE_OFFSET + 500.0
    result = _raycast(sqi, probe_origin, Gf.Vec3d(0, -1, 0), max_probe)
    if result:
        hit_y = float(result[0][1])
        if hit_y <= float(pos[1]) + 50.0:
            return hit_y
    return None


def _discover_sound_locations(stage) -> List[str]:
    world = stage.GetPrimAtPath("/World")
    if not world or not world.IsValid():
        return []
    result = []
    for child in world.GetChildren():
        name = child.GetName()
        if name.startswith("sound_location_") and child.IsValid():
            result.append(str(child.GetPath()))
    result.sort()
    return result


# ── Radial wall-distance scan ──────────────────────────────────────────────────


def _has_floor_at(sqi, x: float, z: float, ground_y: float) -> bool:
    """Check if a walkable floor surface exists at (x, z) near ground_y.
    Probes from 10 cm above ground_y, max 40 cm down.  Only upward-facing
    surfaces (normal Y >= MIN_FLOOR_NORMAL_Y) count — seat backs, railings,
    and armrests are ignored."""
    start_y = ground_y + 10.0
    probe = Gf.Vec3d(x, start_y, z)
    result = _raycast(sqi, probe, Gf.Vec3d(0, -1, 0), FLOOR_TOLERANCE + 10.0)
    if result is None:
        return False
    _, normal = result
    return float(normal[1]) >= MIN_FLOOR_NORMAL_Y


def _radial_wall_scan(
    sqi, center: Gf.Vec3d, ground_y: float, max_radius: float,
) -> List[Tuple[float, float]]:
    """Pure horizontal raycasting + floor-edge clipping.

    1. Horizontal ray per angle → wall_dist (or max_radius on miss).
    2. Check if floor exists under the boundary point.
    3. If no floor → binary-search inward to find the floor edge,
       truncate boundary there.  Prevents the polygon from flowing
       over ledges, balconies, and arena edges.

    Returns ordered (x, z) boundary points — one per angle."""
    ray_y = ground_y + RAY_HEIGHT
    cx, cz = float(center[0]), float(center[2])
    boundary_xz: List[Tuple[float, float]] = []
    wall_hits = 0
    cliff_clips = 0

    for i in range(NUM_H_RAYS):
        angle = 2.0 * math.pi * i / NUM_H_RAYS
        dx = math.cos(angle)
        dz = math.sin(angle)

        origin = Gf.Vec3d(cx, ray_y, cz)
        direction = Gf.Vec3d(dx, 0.0, dz)

        hit = _raycast(sqi, origin, direction, max_radius)
        if hit:
            pos, _ = hit
            xz_dist = math.sqrt((float(pos[0]) - cx) ** 2 + (float(pos[2]) - cz) ** 2)
            r = max(xz_dist - WALL_INSET, MIN_BOUNDARY)
            wall_hits += 1
        else:
            r = max_radius

        bx = cx + dx * r
        bz = cz + dz * r

        if not _has_floor_at(sqi, bx, bz, ground_y):
            cliff_clips += 1
            lo, hi = 0.0, r
            for _ in range(CLIFF_SEARCH_STEPS):
                mid = (lo + hi) * 0.5
                mx = cx + dx * mid
                mz = cz + dz * mid
                if _has_floor_at(sqi, mx, mz, ground_y):
                    lo = mid
                else:
                    hi = mid
            r = max(lo, MIN_BOUNDARY)
            bx = cx + dx * r
            bz = cz + dz * r

        boundary_xz.append((bx, bz))

    print(f"[sound_areas] radial scan: {wall_hits}/{NUM_H_RAYS} wall hits, "
          f"{cliff_clips} floor-edge clips, ground_y={ground_y:.1f}")
    return boundary_xz


# ── USD helpers ────────────────────────────────────────────────────────────────


def _ensure_material(stage, layer, loc_name: str, color_index: int):
    mat_path = f"{SOUND_AREAS_ROOT}/Material_{loc_name}"
    prim = stage.GetPrimAtPath(mat_path)
    if prim and prim.IsValid():
        mat = UsdShade.Material(prim)
        if mat:
            return mat

    diffuse, emul = _SOUND_COLORS[color_index % len(_SOUND_COLORS)]
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
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.4)
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _create_footprint_mesh(stage, layer, prim_path, boundary_xz, center_xz, ground_y, material, area_name: str = ""):
    """Create a flat triangulated polygon (fan from sound source center).
    Vertices are ordered by angle so concave shapes work correctly."""
    n = len(boundary_xz)
    if n < 3:
        return
    y = ground_y + GROUND_OFFSET

    points = [Gf.Vec3f(float(x), float(y), float(z)) for x, z in boundary_xz]
    points.append(Gf.Vec3f(float(center_xz[0]), float(y), float(center_xz[1])))
    center_idx = n

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


def get_sound_location_names() -> Dict[str, str]:
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return {}
    return {
        p.rsplit("/", 1)[-1]: _area_name(p.rsplit("/", 1)[-1])
        for p in _discover_sound_locations(stage)
    }


def _area_name(loc_name: str) -> str:
    return f"{loc_name}_area"


def _build_area_for_location(
    stage, sqi, edit_layer, loc_path: str, loc_idx: int,
) -> Optional[str]:
    loc_name = loc_path.rsplit("/", 1)[-1]
    mesh_path = f"{SOUND_AREAS_ROOT}/{loc_name}"

    prim = stage.GetPrimAtPath(loc_path)
    if not prim or not prim.IsValid():
        return None
    xformable = UsdGeom.Xformable(prim)
    world_mtx = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    pos = Gf.Vec3d(world_mtx.ExtractTranslation())

    ground_y = float(pos[1])
    if sqi:
        gy = _find_ground_y(sqi, pos)
        if gy is not None:
            ground_y = gy

    cx, cz = float(pos[0]), float(pos[2])

    if sqi:
        boundary_xz = _radial_wall_scan(sqi, pos, ground_y, FIXED_RADIUS)
    else:
        boundary_xz = []
        for i in range(NUM_H_RAYS):
            angle = 2.0 * math.pi * i / NUM_H_RAYS
            boundary_xz.append((cx + FIXED_RADIUS * math.cos(angle), cz + FIXED_RADIUS * math.sin(angle)))

    if len(boundary_xz) < 3:
        return None

    with Usd.EditContext(stage, edit_layer):
        root = stage.GetPrimAtPath(SOUND_AREAS_ROOT)
        if not root or not root.IsValid():
            stage.DefinePrim(SOUND_AREAS_ROOT, "Xform")

    area = _area_name(loc_name)
    material = _ensure_material(stage, edit_layer, loc_name, loc_idx)
    _create_footprint_mesh(stage, edit_layer, mesh_path, boundary_xz, (cx, cz), ground_y, material, area_name=area)
    return loc_name


def ensure_sound_areas() -> List[str]:
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return []

    locations = _discover_sound_locations(stage)
    if not locations:
        print("[sound_areas] No sound_location_* prims found under /World")
        return []

    sqi = _get_physx_sqi()
    edit_layer = _get_edit_layer(stage)

    with Usd.EditContext(stage, edit_layer):
        root = stage.GetPrimAtPath(SOUND_AREAS_ROOT)
        if not root or not root.IsValid():
            stage.DefinePrim(SOUND_AREAS_ROOT, "Xform")

    created: List[str] = []
    for loc_idx, loc_path in enumerate(locations):
        result = _build_area_for_location(stage, sqi, edit_layer, loc_path, loc_idx)
        if result:
            created.append(result)

    if created:
        print(f"[sound_areas] Created {len(created)} sound area meshes")
    return created


def set_sound_areas_visible(visible: bool) -> None:
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return
    root = stage.GetPrimAtPath(SOUND_AREAS_ROOT)
    if not root or not root.IsValid():
        if visible:
            ensure_sound_areas()
            root = stage.GetPrimAtPath(SOUND_AREAS_ROOT)
            if not root or not root.IsValid():
                return
        else:
            return
    from younite.payload_orchestrator_core_extension import show_hide, Priority
    if not show_hide(SOUND_AREAS_ROOT, visible, Priority.MEDIUM, source="sound_areas"):
        imageable = UsdGeom.Imageable(root)
        if imageable:
            if visible:
                imageable.MakeVisible()
            else:
                imageable.MakeInvisible()


def remove_sound_areas() -> List[str]:
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return []
    names = list(get_sound_location_names().values())
    root = stage.GetPrimAtPath(SOUND_AREAS_ROOT)
    if root and root.IsValid():
        edit_layer = _get_edit_layer(stage)
        with Usd.EditContext(stage, edit_layer):
            stage.RemovePrim(SOUND_AREAS_ROOT)
        root_layer = stage.GetRootLayer()
        if root_layer and root_layer != edit_layer:
            stale_spec = root_layer.GetPrimAtPath(SOUND_AREAS_ROOT)
            if stale_spec:
                parent_spec = stale_spec.nameParent
                if parent_spec:
                    del parent_spec.nameChildren[stale_spec.name]
    return names
