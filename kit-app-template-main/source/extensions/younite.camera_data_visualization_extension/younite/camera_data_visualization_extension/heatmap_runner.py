"""
Heatmap visualization for camera data (GDPR-friendly).
- Uses detection messages only (array of humans per timestamp), no tracker IDs.
- Builds a 2D density grid with exponential decay and smooth Gaussian falloff.
- Uses displayColor primvar on a subdivided mesh (no texture files) for reliable updates.
- Mesh is dynamically created at the camera's ground footprint location.
- Hull masking ensures heatmap colors only appear within the camera coverage area.
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Optional, List, Any, Dict, Tuple
from datetime import datetime

import numpy as np

import omni.kit.app
import omni.usd
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf

HEATMAP_GRID_W = 64
HEATMAP_GRID_H = 64
HEATMAP_FPS = 5.0
HEATMAP_DECAY = 0.92
HEATMAP_ADD_SCALE = 2.0
HEATMAP_GAUSSIAN_SIGMA = 1.5
HEATMAP_GAMMA = 0.6
HEATMAP_BG_BRIGHTNESS = 0.2
PLAY_EVERY_NTH = 1
FRAMES_PER_TICK = 4


def _parse_message_ts_ms(msg: dict) -> Optional[int]:
    iso_ts = msg.get("timestamp", "")
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def load_detection_frames(json_path: str) -> Tuple[List[int], Dict[int, List[Tuple[float, float]]]]:
    p = Path(json_path)
    with p.open("r", encoding="utf-8") as f:
        messages = json.load(f)
    by_ts: Dict[int, List[Tuple[float, float]]] = defaultdict(list)
    for msg in messages:
        topic = msg.get("topic", "")
        if "dataq/detections/" not in topic:
            continue
        payload_parsed = msg.get("payload_parsed", {})
        detection_list = payload_parsed.get("list", [])
        if not isinstance(detection_list, list):
            continue
        msg_ts_ms = _parse_message_ts_ms(msg)
        if msg_ts_ms is None:
            continue
        for det in detection_list:
            if not isinstance(det, dict):
                continue
            if (
                det.get("class") != "Human"
                or det.get("ignore", False)
                or "x" not in det
                or "y" not in det
            ):
                continue
            try:
                x = float(det.get("x", 0.0))
                y = float(det.get("y", 0.0))
                by_ts[msg_ts_ms].append((x, y))
            except Exception:
                continue
    timestamps = sorted(by_ts.keys())
    print(f"[Heatmap] load_detection_frames: {len(timestamps)} frames")
    return timestamps, dict(by_ts)


def load_detection_frames_from_data(messages: List[Any]) -> Tuple[List[int], Dict[int, List[Tuple[float, float]]]]:
    by_ts: Dict[int, List[Tuple[float, float]]] = defaultdict(list)
    for msg in messages:
        topic = msg.get("topic", "")
        if "dataq/detections/" not in topic:
            continue
        payload_parsed = msg.get("payload_parsed", {})
        detection_list = payload_parsed.get("list", [])
        if not isinstance(detection_list, list):
            continue
        msg_ts_ms = _parse_message_ts_ms(msg)
        if msg_ts_ms is None:
            continue
        for det in detection_list:
            if not isinstance(det, dict):
                continue
            if (
                det.get("class") != "Human"
                or det.get("ignore", False)
                or "x" not in det
                or "y" not in det
            ):
                continue
            try:
                x = float(det.get("x", 0.0))
                y = float(det.get("y", 0.0))
                by_ts[msg_ts_ms].append((x, y))
            except Exception:
                continue
    return sorted(by_ts.keys()), dict(by_ts)




def _gaussian_kernel(sigma: float, half_size: int) -> np.ndarray:
    ax = np.arange(-half_size, half_size + 1, dtype=np.float64)
    gx = np.exp(-0.5 * (ax / sigma) ** 2)
    g = gx[:, None] * gx[None, :]
    return g / g.sum()


_cached_kernel: Optional[np.ndarray] = None
_cached_kernel_sigma: Optional[float] = None


def _get_cached_kernel(sigma: float) -> np.ndarray:
    global _cached_kernel, _cached_kernel_sigma
    if _cached_kernel is not None and _cached_kernel_sigma == sigma:
        return _cached_kernel
    half = max(2, int(sigma * 3))
    _cached_kernel = _gaussian_kernel(sigma, half)
    _cached_kernel_sigma = sigma
    return _cached_kernel


def _add_detections_to_grid(
    grid: np.ndarray,
    points: List[Tuple[float, float]],
    bbox: Tuple[float, float, float, float],
    detection_map: Optional[Dict],
    add_scale: float,
    sigma: float,
) -> None:
    """Map each detection (x,y) to world position via raycasted detection_map,
    then place it in the correct grid cell based on the footprint bbox."""
    from .camera_footprint import map_detection_to_world

    min_x, max_x, min_z, max_z = bbox
    span_x = max(max_x - min_x, 1.0)
    span_z = max(max_z - min_z, 1.0)
    h, w = grid.shape
    kernel = _get_cached_kernel(sigma)
    kh, kw = kernel.shape

    for (det_x, det_y) in points:
        if detection_map is None:
            continue
        world_pos = map_detection_to_world(det_x, det_y, detection_map)
        if world_pos is None:
            continue
        wx, _, wz = world_pos

        u = (wx - min_x) / span_x
        v = (wz - min_z) / span_z
        if u < 0 or u > 1 or v < 0 or v > 1:
            continue
        cx = int(u * (w - 1))
        cy = int(v * (h - 1))
        r0 = max(0, cy - kh // 2)
        r1 = min(h, cy + kh // 2 + 1)
        c0 = max(0, cx - kw // 2)
        c1 = min(w, cx + kw // 2 + 1)
        kr0 = r0 - (cy - kh // 2)
        kr1 = kr0 + (r1 - r0)
        kc0 = c0 - (cx - kw // 2)
        kc1 = kc0 + (c1 - c0)
        grid[r0:r1, c0:c1] += add_scale * kernel[kr0:kr1, kc0:kc1]


def _build_hull_mask(
    hull_xz: List[Tuple[float, float]],
    bbox: Tuple[float, float, float, float],
    grid_w: int,
    grid_h: int,
) -> np.ndarray:
    """Pre-compute boolean mask: True if vertex is inside the convex hull."""
    from .camera_footprint import point_in_convex_hull

    min_x, max_x, min_z, max_z = bbox
    mask = np.zeros(((grid_h + 1), (grid_w + 1)), dtype=np.bool_)
    for row in range(grid_h + 1):
        for col in range(grid_w + 1):
            wx = min_x + (col / grid_w) * (max_x - min_x)
            wz = min_z + (row / grid_h) * (max_z - min_z)
            mask[row, col] = point_in_convex_hull(wx, wz, hull_xz)
    return mask


def _grid_to_display_colors(grid: np.ndarray, hull_mask: Optional[np.ndarray] = None) -> np.ndarray:
    """Convert density grid to RGB for displayColor primvar (vertex interpolation).

    Vertices outside the hull mask get near-zero color to blend with ground.
    """
    g = np.asarray(grid, dtype=np.float64)
    nw, nh = HEATMAP_GRID_W, HEATMAP_GRID_H
    nv = (nw + 1) * (nh + 1)
    bg = HEATMAP_BG_BRIGHTNESS

    if g.size == 0:
        rgb = np.empty((nv, 3), dtype=np.float32)
        rgb[:] = (0, 0, bg)
        return rgb

    gmax = float(np.max(g))
    if gmax <= 0:
        rgb = np.empty((nv, 3), dtype=np.float32)
        rgb[:] = (0, 0, bg)
        if hull_mask is not None:
            flat_mask = hull_mask.reshape(nv)
            rgb[~flat_mask] = (0.02, 0.02, 0.02)
        return rgb

    g = np.clip(g / gmax, 0, 1)
    g = np.power(g, HEATMAP_GAMMA)

    r = np.clip(np.where(g < 0.5, 4 * g - 1, 1), 0, 1)
    gr = np.clip(np.where(g < 0.25, 4 * g, np.where(g < 0.75, 1, 3 - 4 * g)), 0, 1)
    b = np.clip(np.where(g < 0.25, 1, np.where(g < 0.5, 2 - 4 * g, 0)), 0, 1)

    mask = g > 0.01
    r = np.where(mask, r, bg * 0.2)
    gr = np.where(mask, gr, bg * 0.2)
    b = np.where(mask, b, bg)

    cell_rgb = np.stack([r, gr, b], axis=-1).astype(np.float32)

    padded = np.zeros((nh + 2, nw + 2, 3), dtype=np.float32)
    padded[1:-1, 1:-1] = cell_rgb

    ones = np.zeros((nh + 2, nw + 2), dtype=np.float32)
    ones[1:-1, 1:-1] = 1.0

    v_sum = (padded[:-1, :-1] + padded[1:, :-1] + padded[:-1, 1:] + padded[1:, 1:])
    v_cnt = (ones[:-1, :-1] + ones[1:, :-1] + ones[:-1, 1:] + ones[1:, 1:])

    v_cnt = np.maximum(v_cnt, 1)[:, :, None]
    vertex_rgb = v_sum / v_cnt

    zero_mask = (v_cnt[:, :, 0] == 0)
    if np.any(zero_mask):
        vertex_rgb[zero_mask] = [0, 0, bg]

    result = vertex_rgb.reshape(nv, 3)

    # Apply hull mask: outside-hull vertices get near-black
    if hull_mask is not None:
        flat_mask = hull_mask.reshape(nv)
        result[~flat_mask] = (0.02, 0.02, 0.02)

    return result


def _create_heatmap_grid_mesh(
    stage,
    mesh_path: str,
    bbox: Tuple[float, float, float, float],
    ground_y: float,
    existing_prim=None,
) -> UsdGeom.Mesh:
    """Create a subdivided grid mesh positioned at the camera's ground footprint."""
    nw, nh = HEATMAP_GRID_W, HEATMAP_GRID_H
    nv = (nw + 1) * (nh + 1)
    nf = nw * nh

    min_x, max_x, min_z, max_z = bbox
    y = ground_y + 1.0

    points = []
    for row in range(nh + 1):
        for col in range(nw + 1):
            x = min_x + (col / nw) * (max_x - min_x)
            z = min_z + (row / nh) * (max_z - min_z)
            points.append(Gf.Vec3f(float(x), float(y), float(z)))

    face_vertex_counts = [4] * nf
    face_vertex_indices = []
    for row in range(nh):
        for col in range(nw):
            v0 = col + row * (nw + 1)
            v1 = v0 + 1
            v2 = v0 + (nw + 1) + 1
            v3 = v0 + (nw + 1)
            face_vertex_indices.extend([v0, v1, v2, v3])

    if existing_prim and existing_prim.IsValid():
        mesh = UsdGeom.Mesh(existing_prim)
    else:
        mesh = UsdGeom.Mesh.Define(stage, mesh_path)

    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(face_vertex_counts)
    mesh.CreateFaceVertexIndicesAttr(face_vertex_indices)
    mesh.CreateExtentAttr([
        Gf.Vec3f(float(min_x), float(y), float(min_z)),
        Gf.Vec3f(float(max_x), float(y), float(max_z)),
    ])
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    normals = [(0, 1, 0)] * (nf * 4)
    mesh.CreateNormalsAttr(normals)

    display_color = UsdGeom.Primvar(mesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex))
    display_color.SetInterpolation(UsdGeom.Tokens.vertex)
    initial_colors = [(0, 0, HEATMAP_BG_BRIGHTNESS)] * nv
    display_color.Set(initial_colors)

    try:
        prim = stage.GetPrimAtPath(mesh_path)
        if prim and prim.HasAPI(UsdShade.MaterialBindingAPI):
            UsdShade.MaterialBindingAPI(prim).UnbindDirectBinding()
    except Exception:
        pass

    print(f"[Heatmap] Created grid mesh at {mesh_path}: {nw}x{nh} cells, "
          f"bbox=({min_x:.0f},{min_z:.0f})-({max_x:.0f},{max_z:.0f}), y={y:.1f}")
    return mesh


# ── State and playback ──
_heatmap_subscription = None
_heatmap_state = {
    "timestamps": [],
    "frames": {},
    "idx": 0,
    "accum": 0.0,
    "dt_target": 1.0 / HEATMAP_FPS,
    "grid": None,
    "bbox": None,
    "detection_map": None,
    "playing": False,
    "camera_id": None,
    "heatmap_prim_path": None,
    "hull_mask": None,
}


def start_heatmap(
    timestamps: List[int],
    frames: Dict[int, List[Tuple[float, float]]],
    camera_id: str = "camera_main_entrance_exit",
    footprint: Optional[Dict] = None,
    texture_dir: Optional[Path] = None,
    detection_map: Optional[Dict] = None,
) -> None:
    global _heatmap_subscription
    stage = omni.usd.get_context().get_stage()
    if not stage:
        raise RuntimeError("No USD stage.")

    if not footprint:
        raise RuntimeError("Footprint data required for heatmap visualization.")

    bbox = footprint["bbox"]
    ground_y = footprint["ground_y"]
    hull_xz = footprint["hull_xz"]

    hp = f"/World/{camera_id}_heatmap"

    prim = stage.GetPrimAtPath(hp)
    if prim and prim.IsValid():
        stage.RemovePrim(hp)

    _create_heatmap_grid_mesh(stage, hp, bbox, ground_y)

    hull_mask = _build_hull_mask(hull_xz, bbox, HEATMAP_GRID_W, HEATMAP_GRID_H)

    _heatmap_state["timestamps"] = timestamps
    _heatmap_state["frames"] = frames
    _heatmap_state["idx"] = 0
    _heatmap_state["accum"] = 0.0
    _heatmap_state["grid"] = np.zeros((HEATMAP_GRID_H, HEATMAP_GRID_W), dtype=np.float64)
    _heatmap_state["bbox"] = bbox
    _heatmap_state["detection_map"] = detection_map
    _heatmap_state["playing"] = True
    _heatmap_state["camera_id"] = camera_id
    _heatmap_state["heatmap_prim_path"] = hp
    _heatmap_state["hull_mask"] = hull_mask

    import carb.eventdispatcher
    ed = carb.eventdispatcher.get_eventdispatcher()
    _heatmap_subscription = ed.observe_event(
        observer_name="younite.camera_data_visualization_extension/heatmap/update",
        event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
        on_event=_heatmap_on_update,
        order=0,
    )
    print(f"[Heatmap] Started: {len(timestamps)} frames, prim={hp}, "
          f"detection_map={'yes' if detection_map else 'NO'}")


def stop_heatmap() -> None:
    global _heatmap_subscription
    _heatmap_state["playing"] = False
    if _heatmap_subscription:
        _heatmap_subscription = None

    hp = _heatmap_state.get("heatmap_prim_path")
    if hp:
        try:
            stage = omni.usd.get_context().get_stage()
            if stage:
                prim = stage.GetPrimAtPath(hp)
                if prim and prim.IsValid():
                    stage.RemovePrim(hp)
                    print(f"[Heatmap] Removed mesh prim {hp}")
        except Exception as e:
            print(f"[Heatmap] Error removing prim: {e}")

    _heatmap_state["grid"] = None
    _heatmap_state["bbox"] = None
    _heatmap_state["detection_map"] = None
    _heatmap_state["camera_id"] = None
    _heatmap_state["heatmap_prim_path"] = None
    _heatmap_state["hull_mask"] = None
    print("[Heatmap] Stopped.")


def _heatmap_on_update(e) -> None:
    stage = omni.usd.get_context().get_stage()
    if not stage or not _heatmap_state["playing"]:
        return
    dt = float(getattr(e, "dt", 0.0)) if e else 0.0
    if dt <= 0:
        dt = 1.0 / 60.0
    _heatmap_state["accum"] += dt
    if _heatmap_state["accum"] < _heatmap_state["dt_target"]:
        return
    _heatmap_state["accum"] = 0.0
    timestamps = _heatmap_state["timestamps"]
    grid = _heatmap_state["grid"]
    bbox = _heatmap_state["bbox"]
    detection_map = _heatmap_state["detection_map"]

    for _ in range(FRAMES_PER_TICK):
        idx = _heatmap_state["idx"]
        if idx >= len(timestamps):
            idx = 0
            grid[:] = 0
        _heatmap_state["idx"] = idx + PLAY_EVERY_NTH
        t = timestamps[idx]
        grid *= HEATMAP_DECAY
        points = _heatmap_state["frames"].get(t, [])
        _add_detections_to_grid(grid, points, bbox, detection_map,
                                HEATMAP_ADD_SCALE, HEATMAP_GAUSSIAN_SIGMA)

    rgb = _grid_to_display_colors(grid, hull_mask=_heatmap_state.get("hull_mask"))
    hp = _heatmap_state["heatmap_prim_path"]
    if hp:
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath(hp))
        if mesh:
            display_color = mesh.GetDisplayColorPrimvar()
            if display_color:
                colors = [Gf.Vec3f(*c) for c in rgb.tolist()]
                display_color.Set(colors)


def main(
    camera_id: str = "camera_main_entrance_exit",
    data_source: Optional[List[Any]] = None,
    default_data_path: Optional[Path] = None,
    heatmap_prim_path: Optional[str] = None,
    texture_dir: Optional[Path] = None,
    footprint: Optional[Dict] = None,
    detection_map: Optional[Dict] = None,
) -> None:
    """Entry point: load detections and start heatmap playback."""
    if data_source is not None:
        timestamps, frames = load_detection_frames_from_data(data_source)
    else:
        json_path = default_data_path or Path(__file__).resolve().parent.parent.parent / "data" / "mqtt_messages.json"
        json_path = Path(json_path)
        if not json_path.exists():
            print(f"[Heatmap] ERROR: JSON not found {json_path}")
            return
        timestamps, frames = load_detection_frames(str(json_path))
    if not timestamps:
        print("[Heatmap] No detection frames found.")
        return
    start_heatmap(
        timestamps,
        frames,
        camera_id=camera_id,
        footprint=footprint,
        texture_dir=texture_dir,
        detection_map=detection_map,
    )
