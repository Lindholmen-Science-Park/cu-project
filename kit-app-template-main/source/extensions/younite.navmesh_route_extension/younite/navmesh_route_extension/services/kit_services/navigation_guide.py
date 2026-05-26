"""
Turn-by-turn navigation guide from a walked NavMesh polyline.

Pipeline: Douglas–Peucker in XZ → drop very short edges → local turn angle threshold.
Does not affect pathfinding; only interprets geometry for UI.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

Vec3 = Tuple[float, float, float]

# Stage units are centimetres.
RDP_EPSILON_CM = 150.0
MIN_EDGE_LENGTH_CM = 100.0
TURN_ANGLE_THRESHOLD_DEG = 25.0

# Player projection must be past milestone by this much (cm) before advancing.
MILESTONE_ADVANCE_EPS_CM = 2.0


def _dist_xz(a: Vec3, b: Vec3) -> float:
    dx = b[0] - a[0]
    dz = b[2] - a[2]
    return math.sqrt(dx * dx + dz * dz)


def _dist3(a: Vec3, b: Vec3) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    dz = b[2] - a[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _perpendicular_distance_xz(point: Vec3, line_start: Vec3, line_end: Vec3) -> float:
    x0, z0 = point[0], point[2]
    x1, z1 = line_start[0], line_start[2]
    x2, z2 = line_end[0], line_end[2]
    dx, dz = x2 - x1, z2 - z1
    if dx * dx + dz * dz < 1e-18:
        return math.hypot(x0 - x1, z0 - z1)
    t = max(0.0, min(1.0, ((x0 - x1) * dx + (z0 - z1) * dz) / (dx * dx + dz * dz)))
    px = x1 + t * dx
    pz = z1 + t * dz
    return math.hypot(x0 - px, z0 - pz)


def douglas_peucker_indices(points: List[Vec3], epsilon: float) -> List[int]:
    """Return vertex indices to keep; first and last always kept."""
    n = len(points)
    if n < 2:
        return list(range(n))
    if n == 2:
        return [0, 1]

    stack: List[Tuple[int, int]] = [(0, n - 1)]
    keep = {0, n - 1}

    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        max_d = -1.0
        idx = a
        for i in range(a + 1, b):
            d = _perpendicular_distance_xz(points[i], points[a], points[b])
            if d > max_d:
                max_d = d
                idx = i
        if max_d > epsilon:
            keep.add(idx)
            stack.append((a, idx))
            stack.append((idx, b))

    return sorted(keep)


def merge_short_edges(points: List[Vec3], indices: List[int], min_len: float) -> List[int]:
    """Drop intermediate vertices that create XZ segments shorter than min_len from previous kept."""
    if len(indices) < 2:
        return indices
    merged: List[int] = [indices[0]]
    for k in range(1, len(indices) - 1):
        cur = indices[k]
        last_kept = merged[-1]
        if _dist_xz(points[last_kept], points[cur]) < min_len:
            continue
        merged.append(cur)
    if merged[-1] != indices[-1]:
        merged.append(indices[-1])
    return merged


def signed_turn_deg_at_vertex(p0: Vec3, p1: Vec3, p2: Vec3) -> float:
    """Signed turn angle (deg) at p1 in XZ (atan2 cross vs dot of incoming/outgoing)."""
    v1x = p1[0] - p0[0]
    v1z = p1[2] - p0[2]
    v2x = p2[0] - p1[0]
    v2z = p2[2] - p1[2]
    len1 = math.hypot(v1x, v1z)
    len2 = math.hypot(v2x, v2z)
    if len1 < 1e-6 or len2 < 1e-6:
        return 0.0
    v1x /= len1
    v1z /= len1
    v2x /= len2
    v2z /= len2
    dot = max(-1.0, min(1.0, v1x * v2x + v1z * v2z))
    cross = v1x * v2z - v1z * v2x
    return math.degrees(math.atan2(cross, dot))


def cumulative_distances_cm(points: List[Vec3]) -> List[float]:
    """cum[i] = path length from points[0] to points[i] along the polyline (cm)."""
    if not points:
        return []
    cum: List[float] = [0.0]
    for i in range(len(points) - 1):
        cum.append(cum[-1] + _dist3(points[i], points[i + 1]))
    return cum


def detect_turns(
    points: List[Vec3],
    indices: List[int],
    angle_threshold_deg: float,
) -> List[Tuple[int, str]]:
    """List of (original_path_index, 'left'|'right') for each sharp turn."""
    out: List[Tuple[int, str]] = []
    if len(indices) < 3:
        return out
    for j in range(1, len(indices) - 1):
        i0, i1, i2 = indices[j - 1], indices[j], indices[j + 1]
        ang = signed_turn_deg_at_vertex(points[i0], points[i1], points[i2])
        if abs(ang) >= angle_threshold_deg:
            # Math CCW vs USD/stage XZ + walk direction: classify opposite to raw atan2 sign so UI matches avatar.
            out.append((i1, "right" if ang > 0 else "left"))
    return out


def position_along_polyline_cm(player: Vec3, points: List[Vec3]) -> float:
    """Distance from path start to orthogonal projection of player onto polyline (cm, 3D segment lengths)."""
    if len(points) < 2:
        return 0.0

    px, pz = player[0], player[2]
    best_seg = 0
    best_t = 0.0
    best_dist_sq = float("inf")

    for i in range(len(points) - 1):
        ax, az = points[i][0], points[i][2]
        bx, bz = points[i + 1][0], points[i + 1][2]
        dx, dz = bx - ax, bz - az
        seg_len_sq = dx * dx + dz * dz
        if seg_len_sq < 1e-12:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / seg_len_sq))
        proj_x = ax + t * dx
        proj_z = az + t * dz
        d_sq = (px - proj_x) ** 2 + (pz - proj_z) ** 2
        if d_sq < best_dist_sq:
            best_dist_sq = d_sq
            best_seg = i
            best_t = t

    forward = 0.0
    for i in range(best_seg):
        forward += _dist3(points[i], points[i + 1])
    a = points[best_seg]
    b = points[best_seg + 1]
    seg_len = _dist3(a, b)
    forward += seg_len * best_t
    return forward


def next_maneuver_from_player(
    player: Vec3,
    points: List[Vec3],
    milestones: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Distance (m) and action for the next milestone ahead of the player."""
    if len(points) < 2 or not milestones:
        return None
    s = position_along_polyline_cm(player, points)
    eps = MILESTONE_ADVANCE_EPS_CM
    for m in milestones:
        cum = float(m["cumCm"])
        if cum > s + eps:
            return {
                "meters": max(0.0, (cum - s) / 100.0),
                "action": str(m["action"]),
            }
    return None


def build_navigation_guide(
    points: List[Vec3],
    destination_kind: str,
    *,
    rdp_epsilon_cm: float = RDP_EPSILON_CM,
    min_edge_cm: float = MIN_EDGE_LENGTH_CM,
    angle_threshold_deg: float = TURN_ANGLE_THRESHOLD_DEG,
) -> Optional[Dict[str, Any]]:
    """
    Returns payload for navmeshRouteGuide + milestones for lightweight updates.
    None if path too short.
    """
    if len(points) < 2:
        return None

    cum = cumulative_distances_cm(points)
    total_cm = cum[-1]
    if total_cm < 1e-3:
        return None

    idxs = douglas_peucker_indices(points, rdp_epsilon_cm)
    idxs = merge_short_edges(points, idxs, min_edge_cm)
    turns = detect_turns(points, idxs, angle_threshold_deg)

    milestones: List[Dict[str, Any]] = []
    for orig_i, direction in turns:
        milestones.append({"cumCm": float(cum[orig_i]), "action": f"turn_{direction}"})
    milestones.append({"cumCm": float(total_cm), "action": "approach"})

    steps: List[Dict[str, Any]] = []
    prev_c = 0.0

    if not turns:
        steps.append({"action": "approach", "distanceMeters": round(total_cm / 100.0, 1)})
    else:
        for orig_i, direction in turns:
            tc = cum[orig_i]
            d_m = (tc - prev_c) / 100.0
            if d_m > 0.05:
                steps.append({"action": "straight", "distanceMeters": round(d_m, 1)})
            steps.append({"action": f"turn_{direction}"})
            prev_c = tc
        d_final = (total_cm - prev_c) / 100.0
        if d_final > 0.05:
            steps.append({"action": "straight", "distanceMeters": round(d_final, 1)})
        steps.append({"action": "approach", "distanceMeters": round(max(0.0, d_final), 1)})

    return {
        "destinationKind": destination_kind,
        "totalCm": float(total_cm),
        "totalDistanceMeters": round(total_cm / 100.0, 1),
        "milestones": milestones,
        "steps": steps,
    }
