"""Single-segment path measure: base vs actual costs and crowd/sound deltas."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ....scripts.navmesh_shortest_path import (
    calculate_path_points,
    estimate_walk_time_seconds,
    path_length_cm,
)

from .constants import DEFAULT_WALK_SPEED_M_PER_S
from .costs import any_cost_above_default
from .types import RouteMeasure, Vec3Ref


def compute_route_measure(
    start_ref: Vec3Ref,
    end_ref: Vec3Ref,
    *,
    start_use_ground: bool = True,
    camera_area_costs: Optional[Dict[str, float]] = None,
    sound_area_costs: Optional[Dict[str, float]] = None,
    include_base: bool = True,
    speed_m_per_s: float = DEFAULT_WALK_SPEED_M_PER_S,
    navmesh_override: Optional[object] = None,
) -> Tuple[bool, List[Tuple[float, float, float]], Optional[RouteMeasure], Optional[str]]:
    """
    Compute path and optional measure (base and/or actual).

    When both camera_area_costs and sound_area_costs have non-default values,
    an intermediate camera-only path is computed to break down contributions:
      crowd_delta = camera_only - base
      sound_delta = actual - camera_only

    When ``navmesh_override`` is provided, all internal path queries run
    against that cached ``INavMesh`` handle (see ``NavMeshModeCache``).

    Returns:
        (success, points_actual, measure_or_none, error_message)
        - points_actual: path points with all costs applied (for drawing/waypoints).
        - measure: populated when include_base or always (actual from points_actual).
    """
    measure = RouteMeasure() if include_base else None
    cam_costs = camera_area_costs or {}
    snd_costs = sound_area_costs or {}
    all_costs: Dict[str, float] = {}
    if cam_costs:
        all_costs.update(cam_costs)
    if snd_costs:
        all_costs.update(snd_costs)

    has_crowd = any_cost_above_default(cam_costs)
    has_sound = any_cost_above_default(snd_costs)

    # POI / exit batch lists almost always run with no crowd or sound costs.
    # In that case the legacy path called ``calculate_path_points`` twice with
    # identical parameters (base + "actual"), doubling NavMesh work per target.
    if include_base and not has_crowd and not has_sound:
        success, points_gf, error = calculate_path_points(
            start_ref,
            end_ref,
            start_use_ground=start_use_ground,
            camera_area_costs=None,
            navmesh_override=navmesh_override,
        )
        if not success:
            return False, [], measure, error
        points = [(float(p[0]), float(p[1]), float(p[2])) for p in points_gf]
        if points_gf:
            len_cm = path_length_cm(points_gf)
            d = len_cm / 100.0
            tsec = estimate_walk_time_seconds(len_cm, speed_m_per_s)
            measure.distance_meters_base = d
            measure.estimated_time_seconds_base = tsec
            measure.distance_meters_actual = d
            measure.estimated_time_seconds_actual = tsec
        return True, points, measure, None

    if include_base:
        success_base, points_base_gf, _ = calculate_path_points(
            start_ref,
            end_ref,
            start_use_ground=start_use_ground,
            camera_area_costs=None,
            navmesh_override=navmesh_override,
        )
        if success_base and points_base_gf and measure is not None:
            len_cm_base = path_length_cm(points_base_gf)
            measure.distance_meters_base = len_cm_base / 100.0
            measure.estimated_time_seconds_base = estimate_walk_time_seconds(len_cm_base, speed_m_per_s)

    cam_only_dist: Optional[float] = None
    cam_only_time: Optional[float] = None
    if include_base and has_crowd and has_sound:
        success_cam, points_cam_gf, _ = calculate_path_points(
            start_ref,
            end_ref,
            start_use_ground=start_use_ground,
            camera_area_costs=cam_costs,
            navmesh_override=navmesh_override,
        )
        if success_cam and points_cam_gf:
            len_cm_cam = path_length_cm(points_cam_gf)
            cam_only_dist = len_cm_cam / 100.0
            cam_only_time = estimate_walk_time_seconds(len_cm_cam, speed_m_per_s)

    success, points_gf, error = calculate_path_points(
        start_ref,
        end_ref,
        start_use_ground=start_use_ground,
        camera_area_costs=all_costs if all_costs else None,
        navmesh_override=navmesh_override,
    )
    if not success:
        return False, [], (measure if include_base else None), error

    points = [(float(p[0]), float(p[1]), float(p[2])) for p in points_gf]
    if measure is None:
        measure = RouteMeasure()
    if points_gf:
        len_cm_actual = path_length_cm(points_gf)
        measure.distance_meters_actual = len_cm_actual / 100.0
        measure.estimated_time_seconds_actual = estimate_walk_time_seconds(len_cm_actual, speed_m_per_s)
        if measure.distance_meters_base == 0 and measure.distance_meters_actual:
            measure.distance_meters_base = measure.distance_meters_actual
            measure.estimated_time_seconds_base = measure.estimated_time_seconds_actual or 0.0

    if not has_crowd and not has_sound and measure is not None:
        measure.distance_meters_actual = measure.distance_meters_base
        measure.estimated_time_seconds_actual = measure.estimated_time_seconds_base

    if include_base and measure is not None:
        base_d = measure.distance_meters_base
        base_t = measure.estimated_time_seconds_base
        actual_d = measure.distance_meters_actual or base_d
        actual_t = measure.estimated_time_seconds_actual or base_t

        if has_crowd and has_sound and cam_only_dist is not None and cam_only_time is not None:
            measure.distance_meters_crowd_delta = max(0.0, cam_only_dist - base_d)
            measure.estimated_time_seconds_crowd_delta = max(0.0, cam_only_time - base_t)
            measure.distance_meters_sound_delta = max(0.0, actual_d - cam_only_dist)
            measure.estimated_time_seconds_sound_delta = max(0.0, actual_t - cam_only_time)
        elif has_crowd and not has_sound:
            measure.distance_meters_crowd_delta = max(0.0, actual_d - base_d)
            measure.estimated_time_seconds_crowd_delta = max(0.0, actual_t - base_t)
            measure.distance_meters_sound_delta = 0.0
            measure.estimated_time_seconds_sound_delta = 0.0
        elif has_sound and not has_crowd:
            measure.distance_meters_crowd_delta = 0.0
            measure.estimated_time_seconds_crowd_delta = 0.0
            measure.distance_meters_sound_delta = max(0.0, actual_d - base_d)
            measure.estimated_time_seconds_sound_delta = max(0.0, actual_t - base_t)

    return True, points, measure, None
