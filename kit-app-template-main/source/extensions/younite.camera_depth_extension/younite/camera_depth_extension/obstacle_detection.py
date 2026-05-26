"""
Obstacle detection by checking point cloud data against the virtual model.

Every captured point sits on a surface at the time of capture.  For each
point a small PhysX overlap-sphere query checks whether collision geometry
still exists at that position.  Points that overlap model geometry are
known — they match the existing virtual scene.  Points with no overlapping
geometry are "ghost points" — they represent real-world obstacles that the
virtual model does not contain.

This approach is independent of the capture camera:
  - **Test data** — virtual capture → remove object → detect ghost
  - **Real-world data** — sensor point cloud imported directly; no virtual
    camera re-cast is needed.

Ghost footprints are projected onto the XZ ground plane, their convex hull
is computed, and the resulting polygon is written as a NavMesh-blocking area
mesh on the navigation sublayer.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import numpy as np

import carb._carb as _carb_c
import omni.physx
import omni.kit.app

_NAV_LAYER_FILENAME = "navigation_layer.usda"
OBSTACLES_PARENT_PATH = "/World/CameraDepthObstacles"
MAX_OBSTACLE_CLUSTERS = 10
OBSTACLE_AREA_NAME = "camera_depth_obstacle"
GROUND_OFFSET = 0.5          # flat mesh sits 0.5 cm above ground

# Overlap check (cm, matching stage units)
CONTACT_RADIUS = 10.0        # sphere radius for overlap contact check

# Clustering
GRID_CELL_SIZE = 25.0        # cm — XZ clustering grid
MIN_POINTS_PER_CLUSTER = 3
AREA_MARGIN = 5.0            # cm — expand hull outward from centroid

# How many points before yielding to the event loop
POINTS_PER_YIELD = 5000


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _find_nav_layer(stage):
    from pxr import Sdf
    root_layer = stage.GetRootLayer()
    for sub_path in root_layer.subLayerPaths:
        if _NAV_LAYER_FILENAME in sub_path:
            layer = Sdf.Layer.FindRelativeToLayer(root_layer, sub_path)
            if layer:
                return layer
    return None


def _raycast_floor_y(
    cx: float, cz: float, start_y: float,
    half_w: float = 0.0, half_d: float = 0.0,
) -> Optional[float]:
    """Cast downward rays at the center (and corners if large enough) and
    return the median hit Y.  Uses a short max distance (200 cm) so the
    ray finds the floor directly below rather than a far-away surface."""
    sq = omni.physx.get_physx_scene_query_interface()
    direction = _carb_c.Float3(0.0, -1.0, 0.0)
    max_dist = 200.0

    samples = [(cx, cz)]
    if half_w > 10.0 and half_d > 10.0:
        iw, id_ = half_w * 0.6, half_d * 0.6
        samples += [
            (cx - iw, cz - id_), (cx + iw, cz - id_),
            (cx - iw, cz + id_), (cx + iw, cz + id_),
        ]

    hits: List[float] = []
    for sx, sz in samples:
        origin = _carb_c.Float3(sx, start_y, sz)
        hit = sq.raycast_closest(origin, direction, max_dist, True)
        if hit and hit.get("hit", False):
            pos = hit.get("position")
            if pos is not None:
                hits.append(float(pos[1]))

    if hits:
        hits.sort()
        return hits[len(hits) // 2]
    return None


# ------------------------------------------------------------------
# 2D convex hull (Andrew's monotone chain — pure numpy)
# ------------------------------------------------------------------

def _convex_hull_2d(points_xz: np.ndarray) -> np.ndarray:
    """Compute the 2D convex hull of an Nx2 array of (x, z) points.

    Returns an Mx2 array of hull vertices in counter-clockwise order.
    Uses Andrew's monotone chain algorithm — O(n log n), no scipy needed.
    """
    order = np.lexsort((points_xz[:, 1], points_xz[:, 0]))
    pts = points_xz[order]

    n = len(pts)
    if n <= 2:
        return pts

    def _cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        tp = (float(p[0]), float(p[1]))
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], tp) <= 0:
            lower.pop()
        lower.append(tp)

    upper: list = []
    for p in reversed(pts):
        tp = (float(p[0]), float(p[1]))
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], tp) <= 0:
            upper.pop()
        upper.append(tp)

    hull = lower[:-1] + upper[:-1]
    return np.array(hull, dtype=np.float64)


def _expand_hull(hull: np.ndarray, margin: float) -> np.ndarray:
    """Push each hull vertex outward from the centroid by *margin* cm."""
    if len(hull) < 3 or margin <= 0:
        return hull

    cx = float(np.mean(hull[:, 0]))
    cz = float(np.mean(hull[:, 1]))

    expanded = hull.copy()
    for i in range(len(expanded)):
        dx = expanded[i, 0] - cx
        dz = expanded[i, 1] - cz
        dist = (dx * dx + dz * dz) ** 0.5
        if dist > 1e-6:
            factor = margin / dist
            expanded[i, 0] += dx * factor
            expanded[i, 1] += dz * factor

    return expanded


# ------------------------------------------------------------------
# Clustering with convex-hull footprints
# ------------------------------------------------------------------

def _cluster_ghost_footprints(
    ghost_points: np.ndarray,
) -> list:
    """Grid-based clustering → convex hull per cluster.

    The grid groups nearby ghost points via BFS flood-fill.  For each
    cluster the 2D convex hull of the XZ footprint is computed and
    expanded outward by ``AREA_MARGIN``.

    Returns a list of tuples:
        (hull_xz, center_x, center_z, half_w, half_d, min_y)

    *hull_xz* — Mx2 ndarray of convex-hull vertices (world XZ coords).
    *half_w / half_d* — bounding-box half-extents (used for floor raycast).
    *min_y* — lowest Y in the cluster (starting height for floor raycast).
    """
    if len(ghost_points) < MIN_POINTS_PER_CLUSTER:
        return []

    xs = ghost_points[:, 0]
    zs = ghost_points[:, 2]

    cell_x = np.floor(xs / GRID_CELL_SIZE).astype(int)
    cell_z = np.floor(zs / GRID_CELL_SIZE).astype(int)

    cells: Dict[Tuple[int, int], List[int]] = {}
    for idx, (cx_i, cz_i) in enumerate(zip(cell_x, cell_z)):
        key = (int(cx_i), int(cz_i))
        cells.setdefault(key, []).append(idx)

    occupied = {k for k, v in cells.items() if len(v) >= MIN_POINTS_PER_CLUSTER}
    if not occupied:
        occupied = {k for k, v in cells.items() if len(v) >= 1}
    if not occupied:
        return []

    # BFS to merge adjacent cells into clusters
    visited: set = set()
    clusters: List[set] = []
    for cell in occupied:
        if cell in visited:
            continue
        cluster: set = set()
        queue = [cell]
        while queue:
            c = queue.pop()
            if c in visited or c not in occupied:
                continue
            visited.add(c)
            cluster.add(c)
            cx, cz = c
            for dx, dz in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nb = (cx + dx, cz + dz)
                if nb in occupied and nb not in visited:
                    queue.append(nb)
        if cluster:
            clusters.append(cluster)

    results: list = []
    for cluster in clusters:
        point_indices: List[int] = []
        for cell in cluster:
            point_indices.extend(cells[cell])
        pts = ghost_points[point_indices]
        min_y = float(np.min(pts[:, 1]))

        xz = pts[:, [0, 2]]
        hull = _convex_hull_2d(xz)

        if len(hull) < 3:
            # Degenerate — fall back to a small rectangle
            x_lo, x_hi = float(np.min(xz[:, 0])), float(np.max(xz[:, 0]))
            z_lo, z_hi = float(np.min(xz[:, 1])), float(np.max(xz[:, 1]))
            if x_hi - x_lo < 10:
                mid = (x_lo + x_hi) * 0.5
                x_lo, x_hi = mid - 5, mid + 5
            if z_hi - z_lo < 10:
                mid = (z_lo + z_hi) * 0.5
                z_lo, z_hi = mid - 5, mid + 5
            hull = np.array([
                [x_lo, z_lo], [x_hi, z_lo],
                [x_hi, z_hi], [x_lo, z_hi],
            ], dtype=np.float64)

        hull = _expand_hull(hull, AREA_MARGIN)

        x_min = float(np.min(hull[:, 0]))
        x_max = float(np.max(hull[:, 0]))
        z_min = float(np.min(hull[:, 1]))
        z_max = float(np.max(hull[:, 1]))
        center_x = (x_min + x_max) * 0.5
        center_z = (z_min + z_max) * 0.5
        half_w = (x_max - x_min) * 0.5
        half_d = (z_max - z_min) * 0.5

        results.append((hull, center_x, center_z, half_w, half_d, min_y))

    return results[:MAX_OBSTACLE_CLUSTERS]


def _ensure_obstacle_material(stage, layer):
    from pxr import Gf, Sdf, Usd, UsdShade

    mat_path = f"{OBSTACLES_PARENT_PATH}/ObstacleMaterial"
    prim = stage.GetPrimAtPath(mat_path)
    if prim and prim.IsValid():
        mat = UsdShade.Material(prim)
        if mat:
            return mat

    with Usd.EditContext(stage, layer):
        mat = UsdShade.Material.Define(stage, mat_path)
        shader = UsdShade.Shader.Define(stage, f"{mat_path}/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(1.0, 0.3, 0.0))
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(1.5, 0.45, 0.0))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.45)
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


# ------------------------------------------------------------------
# Ghost detection (sphere overlap — no camera dependency)
# ------------------------------------------------------------------

async def detect_and_create_areas(
    points_prim_path: str,
) -> int:
    """Detect ghost points via sphere overlap and create NavMesh areas.

    Every captured point sits on a surface.  For each point a small
    overlap-sphere query checks whether collision geometry still exists
    at that position.  Points with no overlapping geometry are ghosts —
    objects present in the point cloud but absent from the virtual model.

    Ghost clusters are projected onto the XZ ground plane and their convex
    hull is used as the NavMesh obstacle area polygon.

    Returns the number of obstacle areas created.
    """
    import omni.usd
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

    stage = omni.usd.get_context().get_stage()
    if not stage:
        raise RuntimeError("No stage available")

    # -- Read captured point cloud --
    pts_prim = stage.GetPrimAtPath(points_prim_path)
    if not pts_prim or not pts_prim.IsValid():
        raise RuntimeError(f"Point cloud prim not found: {points_prim_path}")

    pts = UsdGeom.Points(pts_prim)
    raw_points = pts.GetPointsAttr().Get()
    if not raw_points or len(raw_points) == 0:
        print("[camera_depth] No points in point cloud")
        return 0

    arr = np.array([[p[0], p[1], p[2]] for p in raw_points], dtype=np.float32)
    total = len(arr)

    print(f"[camera_depth] Analyzing {total} points (overlap r={CONTACT_RADIUS} cm)")

    sq = omni.physx.get_physx_scene_query_interface()
    app = omni.kit.app.get_app()

    # ── Overlap check: does collision geometry exist at each point? ──
    ghost_list: List[Tuple[float, float, float]] = []

    for i in range(total):
        px, py, pz = float(arr[i, 0]), float(arr[i, 1]), float(arr[i, 2])
        origin = _carb_c.Float3(px, py, pz)

        found = [False]

        def _on_hit(hit):
            found[0] = True
            return False  # stop after first overlap

        sq.overlap_sphere(CONTACT_RADIUS, origin, _on_hit, False)

        if not found[0]:
            ghost_list.append((px, py, pz))

        if (i + 1) % POINTS_PER_YIELD == 0:
            await app.next_update_async()

    print(f"[camera_depth] {len(ghost_list)} ghost points / {total} total "
          f"({100 * len(ghost_list) / max(total, 1):.1f}%)")

    if not ghost_list:
        print("[camera_depth] No ghost points — all data matches model")
        return 0

    ghost_arr = np.array(ghost_list, dtype=np.float32)

    footprints = _cluster_ghost_footprints(ghost_arr)
    if not footprints:
        print("[camera_depth] Ghost points too scattered to cluster")
        return 0

    print(f"[camera_depth] Clustered into {len(footprints)} obstacle area(s)")

    # -- Remove existing obstacle areas --
    remove_obstacle_areas()

    # -- Create NavMesh area prims --
    nav_layer = _find_nav_layer(stage)
    if not nav_layer:
        print("[camera_depth] Navigation sublayer not found, using root layer")
        nav_layer = stage.GetRootLayer()

    material = _ensure_obstacle_material(stage, nav_layer)
    count = 0

    with Usd.EditContext(stage, nav_layer):
        parent = stage.GetPrimAtPath(OBSTACLES_PARENT_PATH)
        if not parent or not parent.IsValid():
            stage.DefinePrim(OBSTACLES_PARENT_PATH, "Xform")

        for i, (hull_xz, cx, cz, half_w, half_d, cluster_min_y) in enumerate(footprints):
            ray_start = cluster_min_y + 10.0
            gy = _raycast_floor_y(cx, cz, ray_start, half_w, half_d)
            if gy is None:
                gy = cluster_min_y

            obstacle_path = f"{OBSTACLES_PARENT_PATH}/Obstacle_{i:02d}"
            area_path = f"{obstacle_path}/Area"

            stage.DefinePrim(obstacle_path, "Xform")
            xform = UsdGeom.Xformable(stage.GetPrimAtPath(obstacle_path))
            xform.ClearXformOpOrder()
            xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                Gf.Vec3d(cx, gy, cz))

            n_hull = len(hull_xz)
            area_y = GROUND_OFFSET

            mesh_points = []
            for hx, hz in hull_xz:
                mesh_points.append(
                    Gf.Vec3f(float(hx - cx), area_y, float(hz - cz)))
            center_idx = n_hull
            mesh_points.append(Gf.Vec3f(0, area_y, 0))

            face_vertex_counts = [3] * n_hull
            face_vertex_indices = []
            for j in range(n_hull):
                face_vertex_indices.extend(
                    [j, center_idx, (j + 1) % n_hull])

            normals = [Gf.Vec3f(0, 1, 0)] * (n_hull * 3)

            area_prim = stage.DefinePrim(area_path, "Mesh")
            mesh = UsdGeom.Mesh(area_prim)
            mesh.CreatePointsAttr().Set(mesh_points)
            mesh.CreateFaceVertexCountsAttr().Set(face_vertex_counts)
            mesh.CreateFaceVertexIndicesAttr().Set(face_vertex_indices)
            mesh.CreateNormalsAttr().Set(normals)
            mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
            mesh.CreateDoubleSidedAttr().Set(True)
            mesh.CreateSubdivisionSchemeAttr().Set("none")

            UsdShade.MaterialBindingAPI.Apply(area_prim)
            UsdShade.MaterialBindingAPI(area_prim).Bind(material)

            schemas = Sdf.TokenListOp()
            schemas.prependedItems = ["MaterialBindingAPI", "NavMeshAreaAPI"]
            area_prim.SetMetadata("apiSchemas", schemas)
            area_prim.CreateAttribute("nav:area", Sdf.ValueTypeNames.String).Set(OBSTACLE_AREA_NAME)

            print(f"[camera_depth] Created area {obstacle_path} "
                  f"(area={OBSTACLE_AREA_NAME}, {n_hull}-vertex hull, "
                  f"~{half_w * 2:.0f}x{half_d * 2:.0f} cm, "
                  f"center=({cx:.1f}, {cz:.1f}), floorY={gy:.1f})")
            count += 1

    return count


# ------------------------------------------------------------------
# Cleanup
# ------------------------------------------------------------------

def remove_obstacle_areas() -> int:
    """Remove all camera-depth obstacle prims from the nav layer."""
    try:
        import omni.usd
        from pxr import Sdf, Usd

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return 0

        parent = stage.GetPrimAtPath(OBSTACLES_PARENT_PATH)
        if not parent or not parent.IsValid():
            return 0

        nav_layer = _find_nav_layer(stage) or stage.GetRootLayer()
        children = [c.GetPath().pathString for c in parent.GetChildren()
                    if c.GetName() != "ObstacleMaterial"]
        count = 0

        with Usd.EditContext(stage, nav_layer):
            for path in children:
                stage.RemovePrim(path)
                count += 1
            if count > 0:
                stage.RemovePrim(OBSTACLES_PARENT_PATH)

        root_layer = stage.GetRootLayer()
        if root_layer and root_layer != nav_layer:
            stale = root_layer.GetPrimAtPath(OBSTACLES_PARENT_PATH)
            if stale:
                p = stale.nameParent
                if p:
                    del p.nameChildren[stale.name]

        if count > 0:
            print(f"[camera_depth] Removed {count} obstacle area(s)")
        return count
    except Exception as e:
        print(f"[camera_depth] remove error: {e}")
        import traceback
        traceback.print_exc()
        return 0


def has_obstacle_areas() -> bool:
    """Check if any camera-depth obstacle prims exist on stage."""
    try:
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return False
        parent = stage.GetPrimAtPath(OBSTACLES_PARENT_PATH)
        if not parent or not parent.IsValid():
            return False
        for child in parent.GetChildren():
            if child.GetName() != "ObstacleMaterial":
                return True
        return False
    except Exception:
        return False
