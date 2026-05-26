"""
Camera frustum footprint computation and detection-to-world mapping.

1. compute_camera_footprint(): Shoots an 11x11 ray grid, builds a 2D convex hull
   of floor/wall hits. Returns hull, bounding box, centroid, ground_y.

2. build_detection_map(): Computes frustum ray directions on a dense grid and
   intersects each with a horizontal plane at ground_y + 85cm (bbox center /
   torso height). This avoids wall hits and corrects for parallax from elevated
   cameras. Used to map detection (x, y) to world positions via bilinear interpolation.

Self-contained: no USD prim creation, pure geometry computation.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import omni.usd
from pxr import Gf, Usd, UsdGeom

MAX_RAY_DISTANCE = 1500.0
MIN_GROUND_NORMAL_Y = 0.5

_U_STEPS = [i / 5.0 for i in range(-5, 6)]
_V_STEPS = [-0.9 + i * 1.9 / 10.0 for i in range(11)]



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


def _find_ground_y(sqi, cam_pos: Gf.Vec3d) -> Optional[float]:
    result = _raycast(sqi, cam_pos, Gf.Vec3d(0, -1, 0), 10000.0)
    return result[0][1] if result else None


def _filter_outliers(
    points: List[Tuple[float, float]],
    cam_xz: Tuple[float, float],
    forward_xz: Tuple[float, float],
    factor: float = 5.0,
) -> List[Tuple[float, float]]:
    if len(points) < 5:
        return points
    fx, fz = forward_xz
    cx, cz = cam_xz
    lat_dists: List[float] = []
    for px, pz in points:
        dx, dz = px - cx, pz - cz
        lat = abs(dx * (-fz) + dz * fx)
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


def point_in_convex_hull(px: float, pz: float, hull: List[Tuple[float, float]]) -> bool:
    """Test if a point (px, pz) is inside a convex hull (CCW or CW winding)."""
    n = len(hull)
    if n < 3:
        return False
    positive = 0
    negative = 0
    for i in range(n):
        x1, z1 = hull[i]
        x2, z2 = hull[(i + 1) % n]
        cross = (x2 - x1) * (pz - z1) - (z2 - z1) * (px - x1)
        if cross > 0:
            positive += 1
        elif cross < 0:
            negative += 1
        if positive > 0 and negative > 0:
            return False
    return True


def compute_camera_footprint(camera_prim_path: str) -> Optional[Dict]:
    """
    Compute the ground footprint of a camera by frustum ray scanning.

    Returns dict with hull_xz, ground_y, centroid, bbox — or None on failure.
    """
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        print("[camera_footprint] No stage available")
        return None

    sqi = _get_physx_sqi()
    if not sqi:
        print("[camera_footprint] PhysX not available")
        return None

    prim = stage.GetPrimAtPath(camera_prim_path)
    if not prim or not prim.IsValid():
        print(f"[camera_footprint] Camera prim not found: {camera_prim_path}")
        return None

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
        print(f"[camera_footprint] Camera points straight up/down")
        return None
    forward_xz = (fwd_world[0] / fwd_len, fwd_world[2] / fwd_len)
    cam_xz = (cam_pos[0], cam_pos[2])

    all_xz: List[Tuple[float, float]] = []
    floor_ys: List[float] = []

    for v in _V_STEPS:
        for u in _U_STEPS:
            local_dir = Gf.Vec3d(u * half_h, v * half_v, -1.0).GetNormalized()
            world_dir = rot_mtx.TransformDir(local_dir).GetNormalized()
            result = _raycast(sqi, cam_pos, world_dir, MAX_RAY_DISTANCE)
            if result is not None:
                pos, normal = result
                if normal[1] <= -MIN_GROUND_NORMAL_Y:
                    continue
                all_xz.append((float(pos[0]), float(pos[2])))
                if normal[1] >= MIN_GROUND_NORMAL_Y:
                    floor_ys.append(float(pos[1]))

    if len(all_xz) < 3:
        print(f"[camera_footprint] Too few hit points for {camera_prim_path}")
        return None

    if floor_ys:
        ground_y = sorted(floor_ys)[len(floor_ys) // 2]
    else:
        ground_y = _find_ground_y(sqi, cam_pos)
        if ground_y is None:
            print(f"[camera_footprint] No ground found for {camera_prim_path}")
            return None

    cleaned = _filter_outliers(all_xz, cam_xz, forward_xz)
    hull = _convex_hull_2d(cleaned)

    if len(hull) < 3:
        print(f"[camera_footprint] Degenerate hull for {camera_prim_path}")
        return None

    n = len(hull)
    cx = sum(x for x, _ in hull) / n
    cz = sum(z for _, z in hull) / n
    min_x = min(x for x, _ in hull)
    max_x = max(x for x, _ in hull)
    min_z = min(z for _, z in hull)
    max_z = max(z for _, z in hull)

    print(f"[camera_footprint] Computed footprint for {camera_prim_path}: "
          f"{n} hull vertices, ground_y={ground_y:.1f}, "
          f"bbox=({min_x:.0f},{min_z:.0f})-({max_x:.0f},{max_z:.0f})")

    return {
        "hull_xz": hull,
        "ground_y": float(ground_y),
        "centroid": (float(cx), float(cz)),
        "bbox": (float(min_x), float(max_x), float(min_z), float(max_z)),
    }


# ── Detection-to-world mapping ───────────────────────────────────────────────


def _get_camera_intrinsics(stage, camera_prim_path: str):
    """Extract camera position, rotation matrix, and frustum half-angles."""
    prim = stage.GetPrimAtPath(camera_prim_path)
    if not prim or not prim.IsValid():
        return None

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

    return cam_pos, rot_mtx, half_h, half_v


HUMAN_HEIGHT_CM = 85.0  # bbox center ≈ torso height (half of ~170cm full height)

def build_detection_map(
    camera_prim_path: str,
    det_bounds: Tuple[float, float, float, float],
    grid_res: int = 64,
) -> Optional[Dict]:
    """
    Build a lookup grid mapping detection (x, y) to world ground positions.

    Uses ray-plane intersection instead of PhysX raycasting:
    - First finds ground_y via a single downward raycast from the camera.
    - For each grid point, computes the frustum ray direction and intersects
      it with a horizontal plane at ground_y + HUMAN_HEIGHT_CM.
    - HUMAN_HEIGHT_CM = 85cm (bbox center ≈ torso), since most AI trackers
      report the bounding box center, not the head or feet.

    This solves two problems vs raycasting to geometry:
    1. No wall hits — rays that would hit walls instead land on the
       torso-height plane, giving the correct ground (x, z) position.
    2. Parallax correction — the camera sees a point on the torso, but
       feet are closer to the camera. Intersecting at torso height gives
       the correct foot position directly below.

    det_bounds: (min_x, max_x, min_y, max_y) of the detection data range.
    """
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        print("[detection_map] No stage available")
        return None

    sqi = _get_physx_sqi()
    if not sqi:
        print("[detection_map] PhysX not available")
        return None

    intrinsics = _get_camera_intrinsics(stage, camera_prim_path)
    if not intrinsics:
        print(f"[detection_map] Camera not found: {camera_prim_path}")
        return None

    cam_pos, rot_mtx, half_h, half_v = intrinsics

    ground_y = _find_ground_y(sqi, cam_pos)
    if ground_y is None:
        print(f"[detection_map] No ground found below {camera_prim_path}")
        return None

    head_plane_y = ground_y + HUMAN_HEIGHT_CM

    d_min_x, d_max_x, d_min_y, d_max_y = det_bounds
    print(f"[detection_map] Detection bounds: x=[{d_min_x:.2f}, {d_max_x:.2f}], "
          f"y=[{d_min_y:.2f}, {d_max_y:.2f}], "
          f"ground_y={ground_y:.1f}, head_plane_y={head_plane_y:.1f}, "
          f"cam_y={cam_pos[1]:.1f}")

    n = grid_res + 1
    world_x = np.full((n, n), np.nan, dtype=np.float64)
    world_z = np.full((n, n), np.nan, dtype=np.float64)
    valid_mask = np.zeros((n, n), dtype=np.bool_)

    cam_y = float(cam_pos[1])
    cam_x = float(cam_pos[0])
    cam_z = float(cam_pos[2])

    for row in range(n):
        t_y = row / grid_res
        for col in range(n):
            t_x = col / grid_res

            u = (t_x - 0.5) * 2.0
            v = -((t_y - 0.5) * 2.0)

            local_dir = Gf.Vec3d(u * half_h, v * half_v, -1.0).GetNormalized()
            world_dir = rot_mtx.TransformDir(local_dir).GetNormalized()

            dir_y = float(world_dir[1])
            if abs(dir_y) < 1e-6:
                continue

            t = (head_plane_y - cam_y) / dir_y
            if t <= 0:
                continue

            hit_x = cam_x + float(world_dir[0]) * t
            hit_z = cam_z + float(world_dir[2]) * t

            world_x[row, col] = hit_x
            world_z[row, col] = hit_z
            valid_mask[row, col] = True

    valid_count = int(np.sum(valid_mask))
    if valid_count < 3:
        print(f"[detection_map] Too few valid intersections ({valid_count})")
        return None

    _fill_nans_nearest(world_x, valid_mask)
    _fill_nans_nearest(world_z, valid_mask)

    print(f"[detection_map] Built {grid_res}x{grid_res} map for {camera_prim_path}: "
          f"{valid_count}/{n*n} valid, ground_y={ground_y:.1f}, "
          f"head_plane={head_plane_y:.1f}")

    return {
        "world_x": world_x,
        "world_z": world_z,
        "valid_mask": valid_mask,
        "ground_y": float(ground_y),
        "grid_res": grid_res,
        "det_bounds": det_bounds,
    }


def _fill_nans_nearest(arr: np.ndarray, valid: np.ndarray) -> None:
    """Fill NaN cells by nearest-valid-neighbor (simple iterative dilation)."""
    if np.all(valid):
        return
    filled = valid.copy()
    for _ in range(max(arr.shape)):
        if np.all(filled):
            break
        missing = ~filled
        rows, cols = np.where(missing)
        for r, c in zip(rows, cols):
            neighbors = []
            if r > 0 and filled[r - 1, c]:
                neighbors.append(arr[r - 1, c])
            if r < arr.shape[0] - 1 and filled[r + 1, c]:
                neighbors.append(arr[r + 1, c])
            if c > 0 and filled[r, c - 1]:
                neighbors.append(arr[r, c - 1])
            if c < arr.shape[1] - 1 and filled[r, c + 1]:
                neighbors.append(arr[r, c + 1])
            if neighbors:
                arr[r, c] = sum(neighbors) / len(neighbors)
                filled[r, c] = True


def map_detection_to_world(
    det_x: float,
    det_y: float,
    detection_map: Dict,
) -> Optional[Tuple[float, float, float]]:
    """
    Map a detection (x, y) in its native coordinate system to world (x, y, z).

    First normalizes (det_x, det_y) to 0–1 using the stored det_bounds,
    then uses bilinear interpolation on the pre-computed raycast grid.
    Returns (world_x, ground_y, world_z) or None if out of range.
    """
    grid_res = detection_map["grid_res"]
    world_x = detection_map["world_x"]
    world_z = detection_map["world_z"]
    ground_y = detection_map["ground_y"]
    d_min_x, d_max_x, d_min_y, d_max_y = detection_map["det_bounds"]

    span_x = d_max_x - d_min_x
    span_y = d_max_y - d_min_y
    if span_x <= 0 or span_y <= 0:
        return None

    t_x = (det_x - d_min_x) / span_x
    t_y = (det_y - d_min_y) / span_y

    gx = t_x * grid_res
    gy = t_y * grid_res

    gx = max(0.0, min(float(grid_res), gx))
    gy = max(0.0, min(float(grid_res), gy))

    col0 = int(gx)
    row0 = int(gy)
    col1 = min(col0 + 1, grid_res)
    row1 = min(row0 + 1, grid_res)

    fx = gx - col0
    fy = gy - row0

    wx = (world_x[row0, col0] * (1 - fx) * (1 - fy)
          + world_x[row0, col1] * fx * (1 - fy)
          + world_x[row1, col0] * (1 - fx) * fy
          + world_x[row1, col1] * fx * fy)

    wz = (world_z[row0, col0] * (1 - fx) * (1 - fy)
          + world_z[row0, col1] * fx * (1 - fy)
          + world_z[row1, col0] * (1 - fx) * fy
          + world_z[row1, col1] * fx * fy)

    return (float(wx), float(ground_y), float(wz))
