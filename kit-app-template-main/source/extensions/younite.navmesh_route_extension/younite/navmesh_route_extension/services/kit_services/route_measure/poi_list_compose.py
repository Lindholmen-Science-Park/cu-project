"""Composer-based POI-list routes (shortcut-aware cache population)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ..route_composer import compose_with_measure, get_route_composer
from .constants import DEFAULT_WALK_SPEED_M_PER_S
from .types import RouteMeasure

Point = Tuple[float, float, float]


def measure_dict_to_route_measure(
    measure_dict: Optional[Dict[str, Optional[float]]],
) -> Optional[RouteMeasure]:
    if not measure_dict:
        return None
    return RouteMeasure(
        distance_meters_base=float(measure_dict.get("distance_meters_base") or 0.0),
        estimated_time_seconds_base=float(
            measure_dict.get("estimated_time_seconds_base") or 0.0
        ),
        distance_meters_actual=measure_dict.get("distance_meters_actual"),
        estimated_time_seconds_actual=measure_dict.get(
            "estimated_time_seconds_actual"
        ),
        distance_meters_crowd_delta=measure_dict.get("distance_meters_crowd_delta"),
        estimated_time_seconds_crowd_delta=measure_dict.get(
            "estimated_time_seconds_crowd_delta"
        ),
        distance_meters_sound_delta=measure_dict.get("distance_meters_sound_delta"),
        estimated_time_seconds_sound_delta=measure_dict.get(
            "estimated_time_seconds_sound_delta"
        ),
    )


def compose_poi_list_route(
    player_pos_t: Point,
    end_pos_t: Point,
    *,
    via_points: Optional[List[Point]] = None,
    enable_corridor_routing: bool = False,
    camera_area_costs: Optional[Dict[str, float]] = None,
    sound_area_costs: Optional[Dict[str, float]] = None,
    enable_shortcuts: bool = False,
    prefer_shortcuts: bool = False,
    speed_m_per_s: float = DEFAULT_WALK_SPEED_M_PER_S,
) -> Tuple[
    bool,
    List[Point],
    Optional[RouteMeasure],
    List[Point],
    List[float],
    List[str],
    bool,
    Optional[str],
]:
    """Plan one player→POI path for list display and cache storage.

    Returns
    -------
    success, polyline, measure, via_points_for_route_config,
    segment_speeds, segment_classes, has_shortcut, error
    """
    composer = get_route_composer()
    if composer is None:
        return False, [], None, [], [], [], False, "no route composer"

    vias: Optional[Sequence[Sequence[float]]] = via_points if via_points else None
    try:
        composed, measure_dict = compose_with_measure(
            composer,
            player_pos_t,
            end_pos_t,
            camera_area_costs=camera_area_costs,
            sound_area_costs=sound_area_costs,
            via_points=vias,
            enable_corridor_routing=enable_corridor_routing,
            enable_shortcuts=enable_shortcuts,
            prefer_shortcuts=prefer_shortcuts,
            shortcut_eval_always=bool(enable_shortcuts),
            speed_m_per_s=speed_m_per_s,
            apply_navmesh_validated_straighten=False,
        )
    except Exception as exc:
        return False, [], None, list(via_points or []), [], [], False, str(exc)

    if composed is None or len(composed.polyline) < 2:
        return False, [], None, list(via_points or []), [], [], False, "no walkable route"

    points: List[Point] = [
        (float(p[0]), float(p[1]), float(p[2])) for p in composed.polyline
    ]
    has_shortcut = bool(composed.has_shortcut)
    # Corridor vias are irrelevant once a shortcut hop replaces the walk.
    stored_vias: List[Point] = [] if has_shortcut else list(via_points or [])
    speeds = list(composed.segment_speeds) if composed.segment_speeds else []
    classes = list(composed.segment_classes) if composed.segment_classes else []
    measure = measure_dict_to_route_measure(measure_dict)
    return True, points, measure, stored_vias, speeds, classes, has_shortcut, None
