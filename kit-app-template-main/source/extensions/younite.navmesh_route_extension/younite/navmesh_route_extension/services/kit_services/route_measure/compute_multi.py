"""Multi-segment measure through waypoint chains (``INavMeshPath.length`` per leg)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ....scripts.navmesh_shortest_path import (
    calculate_path_points,
    estimate_walk_time_seconds,
    navmesh_path_length_cm,
    path_length_cm,
    resolve_position,
)

from .constants import DEFAULT_WALK_SPEED_M_PER_S
from .types import RouteMeasure, Vec3Ref


def measure_multi_segment(
    start_ref: Vec3Ref,
    end_ref: Vec3Ref,
    via_points: List[Tuple[float, float, float]],
    *,
    start_use_ground: bool = True,
    camera_area_costs: Optional[Dict[str, float]] = None,
    speed_m_per_s: float = DEFAULT_WALK_SPEED_M_PER_S,
    navmesh_override: Optional[object] = None,
) -> Tuple[bool, Optional[RouteMeasure], Optional[str]]:
    import omni.usd

    ctx = omni.usd.get_context()
    stage = ctx.get_stage() if ctx else None
    if not stage:
        return False, None, "No USD stage"

    try:
        start_gf = resolve_position(stage, start_ref, use_ground=start_use_ground)
        start_t = (float(start_gf[0]), float(start_gf[1]), float(start_gf[2]))
    except Exception as e:
        return False, None, f"Cannot resolve start: {e}"

    try:
        end_gf = resolve_position(stage, end_ref, use_ground=False)
        end_t = (float(end_gf[0]), float(end_gf[1]), float(end_gf[2]))
    except Exception as e:
        return False, None, f"Cannot resolve end: {e}"

    legs: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = []
    legs.append((start_t, via_points[0]))
    for i in range(len(via_points) - 1):
        legs.append((via_points[i], via_points[i + 1]))
    legs.append((via_points[-1], end_t))

    total_cm = 0.0
    for seg_start, seg_end in legs:
        d = navmesh_path_length_cm(
            seg_start,
            seg_end,
            camera_area_costs=camera_area_costs,
            navmesh_override=navmesh_override,
        )
        if d == float("inf"):
            return False, None, "Segment failed in multi-segment measure"
        total_cm += d

    measure = RouteMeasure(
        distance_meters_base=total_cm / 100.0,
        estimated_time_seconds_base=estimate_walk_time_seconds(total_cm, speed_m_per_s),
        distance_meters_actual=total_cm / 100.0,
        estimated_time_seconds_actual=estimate_walk_time_seconds(total_cm, speed_m_per_s),
    )
    return True, measure, None


def multi_segment_path_points(
    start_ref: Vec3Ref,
    end_ref: Vec3Ref,
    via_points: List[Tuple[float, float, float]],
    *,
    start_use_ground: bool = True,
    camera_area_costs: Optional[Dict[str, float]] = None,
    speed_m_per_s: float = DEFAULT_WALK_SPEED_M_PER_S,
    navmesh_override: Optional[object] = None,
) -> Tuple[bool, List[Tuple[float, float, float]], Optional[RouteMeasure], Optional[str]]:
    """Same legs as ``measure_multi_segment``, but returns the merged polyline for caching."""
    import omni.usd

    ctx = omni.usd.get_context()
    stage = ctx.get_stage() if ctx else None
    if not stage:
        return False, [], None, "No USD stage"

    try:
        start_gf = resolve_position(stage, start_ref, use_ground=start_use_ground)
        start_t = (float(start_gf[0]), float(start_gf[1]), float(start_gf[2]))
    except Exception as e:
        return False, [], None, f"Cannot resolve start: {e}"

    try:
        end_gf = resolve_position(stage, end_ref, use_ground=False)
        end_t = (float(end_gf[0]), float(end_gf[1]), float(end_gf[2]))
    except Exception as e:
        return False, [], None, f"Cannot resolve end: {e}"

    if not via_points:
        success, points_gf, error = calculate_path_points(
            start_ref,
            end_ref,
            start_use_ground=start_use_ground,
            camera_area_costs=camera_area_costs,
            navmesh_override=navmesh_override,
        )
        if not success:
            return False, [], None, error
        points = [(float(p[0]), float(p[1]), float(p[2])) for p in points_gf]
        if len(points) < 2:
            return False, [], None, "Path too short"
        len_cm = path_length_cm(points_gf)
        measure = RouteMeasure(
            distance_meters_base=len_cm / 100.0,
            estimated_time_seconds_base=estimate_walk_time_seconds(len_cm, speed_m_per_s),
            distance_meters_actual=len_cm / 100.0,
            estimated_time_seconds_actual=estimate_walk_time_seconds(len_cm, speed_m_per_s),
        )
        return True, points, measure, None

    legs: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = []
    legs.append((start_t, via_points[0]))
    for i in range(len(via_points) - 1):
        legs.append((via_points[i], via_points[i + 1]))
    legs.append((via_points[-1], end_t))

    merged: List[Tuple[float, float, float]] = []
    total_cm = 0.0
    cam_costs = camera_area_costs or {}
    for seg_start, seg_end in legs:
        success, points_gf, error = calculate_path_points(
            seg_start,
            seg_end,
            start_use_ground=False,
            camera_area_costs=cam_costs if cam_costs else None,
            navmesh_override=navmesh_override,
        )
        if not success or not points_gf:
            return False, [], None, error or "Segment path failed"
        seg_pts = [(float(p[0]), float(p[1]), float(p[2])) for p in points_gf]
        d = path_length_cm(points_gf)
        if d == float("inf"):
            return False, [], None, "Segment failed in multi-segment path"
        total_cm += d
        if merged and seg_pts:
            if abs(merged[-1][0] - seg_pts[0][0]) < 1.0 and abs(merged[-1][2] - seg_pts[0][2]) < 1.0:
                merged.extend(seg_pts[1:])
            else:
                merged.extend(seg_pts)
        else:
            merged.extend(seg_pts)

    if len(merged) < 2:
        return False, [], None, "Path too short"
    measure = RouteMeasure(
        distance_meters_base=total_cm / 100.0,
        estimated_time_seconds_base=estimate_walk_time_seconds(total_cm, speed_m_per_s),
        distance_meters_actual=total_cm / 100.0,
        estimated_time_seconds_actual=estimate_walk_time_seconds(total_cm, speed_m_per_s),
    )
    return True, merged, measure, None
