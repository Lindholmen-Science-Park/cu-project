"""Batch player→exit measures for POI / evacuation panels."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

OnProgress = Callable[[List[Dict[str, Any]], bool], None]

from ....scripts.navmesh_shortest_path import resolve_position

from .compute_multi import measure_multi_segment, multi_segment_path_points
from .compute_single import compute_route_measure
from . import poi_list_route_cache
from .constants import DEFAULT_WALK_SPEED_M_PER_S
from .poi_list_compose import compose_poi_list_route
from .resolve import resolve_ref_to_vec3
from .shortcut_fallback import shortcut_fallback_measure
from .types import Vec3Ref


def compute_routes_to_exits(
    player_ref: Vec3Ref,
    exit_refs: List[Union[str, Tuple[float, float, float]]],
    *,
    camera_area_costs: Optional[Dict[str, float]] = None,
    sound_area_costs: Optional[Dict[str, float]] = None,
    speed_m_per_s: float = DEFAULT_WALK_SPEED_M_PER_S,
    use_waypoints: bool = False,
    navmesh_override: Optional[object] = None,
    enable_shortcuts: bool = False,
    prefer_shortcuts: bool = False,
    poi_list_cache_type: Optional[str] = None,
    on_progress: Optional[OnProgress] = None,
) -> List[Dict[str, Any]]:
    """
    One-shot: compute path from player to each exit; return list of measure results sorted by best time.
    Does not create or draw routes.

    When ``use_waypoints`` is True, each target is routed through corridor
    waypoints (via ``plan_route_to_position``).

    When ``poi_list_cache_type`` is set (restroom / quiet-zone lists) and
    ``enable_shortcuts`` is True, each entry is planned via
    ``RouteComposer`` (strict-shortest unless ``prefer_shortcuts``) so
    elevator hops that beat walking appear in the sorted list and in the
    one-shot cache used on ``fromPoiList`` activation. Periodic recalc
    after the user starts walking is unchanged.

    Without a cache type, ``enable_shortcuts`` only retries failed
    direct/waypoint measures via the composer (wheelchair + stairs).
    """
    results: List[Dict[str, Any]] = []
    cam_costs = dict(camera_area_costs or {})
    snd_costs = dict(sound_area_costs or {})
    if poi_list_cache_type:
        poi_list_route_cache.clear_poi_type(poi_list_cache_type)

    stage = None
    player_pos_t: Optional[Tuple[float, float, float]] = None
    if use_waypoints or enable_shortcuts:
        try:
            import omni.usd

            ctx = omni.usd.get_context()
            stage = ctx.get_stage() if ctx else None
            if stage:
                player_pos_t = resolve_ref_to_vec3(stage, player_ref, use_ground=True)
        except Exception:
            player_pos_t = None

    for i, end_ref in enumerate(exit_refs):
        exit_id = str(end_ref) if isinstance(end_ref, str) else f"exit_{i}"
        entry: Dict[str, Any] = {
            "exitRef": end_ref
            if isinstance(end_ref, str)
            else (list(end_ref) if isinstance(end_ref, (list, tuple)) else str(end_ref)),
            "exitId": exit_id,
            "success": False,
            "distanceMetersBase": 0.0,
            "estimatedTimeSecondsBase": 0.0,
            "distanceMetersActual": 0.0,
            "estimatedTimeSecondsActual": 0.0,
        }
        try:
            via_points: List[Tuple[float, float, float]] = []
            if use_waypoints and player_pos_t is not None and stage:
                try:
                    from ..waypoint_router import plan_route_to_position

                    if isinstance(end_ref, str):
                        end_gf = resolve_position(stage, end_ref, use_ground=False)
                        target_t = (float(end_gf[0]), float(end_gf[1]), float(end_gf[2]))
                        via_points = plan_route_to_position(player_pos_t, target_t)
                except Exception:
                    via_points = []

            path_points: List[Tuple[float, float, float]] = []
            segment_speeds: List[float] = []
            segment_classes: List[str] = []
            has_shortcut = False
            err: Optional[str] = None
            success = False
            measure = None
            stored_vias: List[Tuple[float, float, float]] = list(via_points)

            use_compose_for_cache = bool(
                poi_list_cache_type and enable_shortcuts and player_pos_t is not None
            )
            if use_compose_for_cache and stage is not None:
                end_pos_t = resolve_ref_to_vec3(stage, end_ref, use_ground=False)
                if end_pos_t is not None:
                    (
                        success,
                        path_points,
                        measure,
                        stored_vias,
                        segment_speeds,
                        segment_classes,
                        has_shortcut,
                        err,
                    ) = compose_poi_list_route(
                        player_pos_t,
                        end_pos_t,
                        via_points=via_points or None,
                        enable_corridor_routing=bool(use_waypoints and not via_points),
                        camera_area_costs=cam_costs if cam_costs else None,
                        sound_area_costs=snd_costs if snd_costs else None,
                        enable_shortcuts=True,
                        prefer_shortcuts=prefer_shortcuts,
                        speed_m_per_s=speed_m_per_s,
                    )
                else:
                    err = "cannot resolve destination"
            elif via_points:
                success, measure, err = measure_multi_segment(
                    player_ref,
                    end_ref,
                    via_points,
                    start_use_ground=True,
                    camera_area_costs=cam_costs if cam_costs else None,
                    speed_m_per_s=speed_m_per_s,
                    navmesh_override=navmesh_override,
                )
                if success and measure is not None and poi_list_cache_type:
                    ok_pts, path_points, _, err_pts = multi_segment_path_points(
                        player_ref,
                        end_ref,
                        via_points,
                        start_use_ground=True,
                        camera_area_costs=cam_costs if cam_costs else None,
                        speed_m_per_s=speed_m_per_s,
                        navmesh_override=navmesh_override,
                    )
                    if not ok_pts:
                        err = err_pts or err
                        success = False
            else:
                success, path_points, measure, err = compute_route_measure(
                    player_ref,
                    end_ref,
                    start_use_ground=True,
                    camera_area_costs=cam_costs if cam_costs else None,
                    sound_area_costs=snd_costs if snd_costs else None,
                    include_base=True,
                    speed_m_per_s=speed_m_per_s,
                    navmesh_override=navmesh_override,
                )
            if success and measure is not None:
                if poi_list_cache_type and path_points:
                    poi_list_route_cache.store(
                        poi_list_cache_type,
                        player_ref,
                        end_ref,
                        points=path_points,
                        via_points=stored_vias,
                        measure=measure,
                        segment_speeds=segment_speeds or None,
                        segment_classes=segment_classes or None,
                        has_shortcut=has_shortcut,
                    )
                entry["success"] = True
                entry["distanceMetersBase"] = measure.distance_meters_base
                entry["estimatedTimeSecondsBase"] = measure.estimated_time_seconds_base
                entry["distanceMetersActual"] = measure.distance_meters_actual or 0.0
                entry["estimatedTimeSecondsActual"] = measure.estimated_time_seconds_actual or 0.0
                if has_shortcut:
                    entry["viaShortcut"] = True
            elif enable_shortcuts and stage is not None and player_pos_t is not None:
                end_pos_t = resolve_ref_to_vec3(stage, end_ref, use_ground=False)
                if end_pos_t is not None:
                    sc_measure = shortcut_fallback_measure(
                        player_pos_t,
                        end_pos_t,
                        camera_area_costs=cam_costs if cam_costs else None,
                        sound_area_costs=snd_costs if snd_costs else None,
                        speed_m_per_s=speed_m_per_s,
                    )
                    if sc_measure is not None:
                        entry["success"] = True
                        entry["distanceMetersBase"] = sc_measure.distance_meters_base
                        entry["estimatedTimeSecondsBase"] = sc_measure.estimated_time_seconds_base
                        entry["distanceMetersActual"] = sc_measure.distance_meters_actual or 0.0
                        entry["estimatedTimeSecondsActual"] = sc_measure.estimated_time_seconds_actual or 0.0
                        entry["viaShortcut"] = True
                    elif err:
                        entry["error"] = str(err)
                elif err:
                    entry["error"] = str(err)
            elif err:
                entry["error"] = str(err)
        except Exception as e:
            entry["error"] = str(e)
        results.append(entry)
        if on_progress is not None:
            on_progress(list(results), False)

    def sort_key(r: Dict[str, Any]) -> Tuple[float, float]:
        t_actual = r.get("estimatedTimeSecondsActual")
        t_base = r.get("estimatedTimeSecondsBase", 0.0) or 0.0
        if t_actual is not None and t_actual > 0:
            return (t_actual, t_base)
        return (float("inf"), t_base)

    results.sort(key=sort_key)
    if on_progress is not None:
        on_progress(list(results), True)
    return results
