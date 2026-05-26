"""
Cost-aware route measurement on top of :class:`RouteComposer`.

Replaces the legacy ``compute_route_measure`` wrapper that ran two or
three sequential ``calculate_path_points`` calls itself. Now we run the
composer two or three times (with progressively richer cost dicts) and
diff the resulting polyline lengths to obtain the
``RouteMeasure`` breakdown the seat / find-toilets / quiet-zone UI
uses to show "+30 s due to crowd".

Why a separate module:

    * Keeps :mod:`composer` focused on path planning. Measure is a
      caller-driven concern — the composer itself is deterministic
      with respect to the cost dict.
    * Lets the route engine call a single helper instead of running
      its own 1-3 compose cycles per recalc.

Output mirrors :class:`route_measure.types.RouteMeasure` exactly so
the existing dispatch and UI code can consume the result unchanged.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .composer import RouteComposer
from .types import (
    DEFAULT_WALK_SPEED_M_PER_S,
    NAVMESH_SEGMENT_SPEED,
    OSM_SEGMENT_SPEED,
    ComposedRoute,
    Vec3,
)


def _cost_active(costs: Optional[Dict[str, float]]) -> bool:
    """True if any cost value is meaningfully above the default 1.0.

    Mirrors :func:`route_measure.costs.any_cost_above_default` so the
    breakdown logic stays identical.
    """
    if not costs:
        return False
    return any(v > 1.05 for v in costs.values())


def _route_distance_meters(route: ComposedRoute) -> float:
    """Polyline length in meters (XZ only — matches NavMesh measure)."""
    return route.distance_meters


def _route_time_seconds(
    route: ComposedRoute, *, speed_m_per_s: float = DEFAULT_WALK_SPEED_M_PER_S,
) -> float:
    """Walk time in seconds, honoring per-segment OSM/NavMesh speeds.

    Uses the same multipliers as :class:`PointClickAutoMover` so the UI
    shows the same ETA the user actually experiences when walking.
    """
    if not route.polyline or len(route.polyline) < 2:
        return 0.0
    base_cm_s = max(1e-6, speed_m_per_s * 100.0)
    total = 0.0
    speeds = route.segment_speeds or []
    for i in range(1, len(route.polyline)):
        a = route.polyline[i - 1]
        b = route.polyline[i]
        dx = a[0] - b[0]
        dz = a[2] - b[2]
        seg_cm = (dx * dx + dz * dz) ** 0.5
        if seg_cm <= 0.0:
            continue
        mult = (
            speeds[i - 1]
            if (i - 1) < len(speeds)
            else NAVMESH_SEGMENT_SPEED
        )
        if mult <= 0.0:
            mult = NAVMESH_SEGMENT_SPEED
        total += seg_cm / (base_cm_s * mult)
    return total


def compose_with_measure(
    composer: RouteComposer,
    start_world: Sequence[float],
    end_world: Sequence[float],
    *,
    camera_area_costs: Optional[Dict[str, float]] = None,
    sound_area_costs: Optional[Dict[str, float]] = None,
    via_points: Optional[Sequence[Sequence[float]]] = None,
    enable_corridor_routing: bool = False,
    corridor_section: Optional[str] = None,
    enable_shortcuts: bool = False,
    prefer_shortcuts: bool = False,
    shortcut_eval_always: bool = False,
    speed_m_per_s: float = DEFAULT_WALK_SPEED_M_PER_S,
    apply_navmesh_validated_straighten: bool = True,
) -> Tuple[Optional[ComposedRoute], Optional[Dict[str, Optional[float]]]]:
    """Compose ``start → end`` and return ``(route, measure_dict)``.

    ``measure_dict`` is shaped to feed
    :class:`route_measure.types.RouteMeasure` directly, with these
    keys (all optional, ``None`` when not applicable):

        distance_meters_base
        estimated_time_seconds_base
        distance_meters_actual
        estimated_time_seconds_actual
        distance_meters_crowd_delta
        estimated_time_seconds_crowd_delta
        distance_meters_sound_delta
        estimated_time_seconds_sound_delta

    The ``actual`` route (with all costs) is the one that gets drawn
    and dispatched to the auto-mover — the base / cam_only composes
    are diff-only and their polylines are discarded.
    """
    cam = dict(camera_area_costs or {})
    snd = dict(sound_area_costs or {})
    has_crowd = _cost_active(cam)
    has_sound = _cost_active(snd)

    # Always need the base (no-cost) composition for the breakdown
    # and to fall back on if the cost-aware compose fails.
    base_route = composer.compose(
        start_world,
        end_world,
        camera_area_costs=None,
        sound_area_costs=None,
        via_points=via_points,
        enable_corridor_routing=enable_corridor_routing,
        corridor_section=corridor_section,
        enable_shortcuts=enable_shortcuts,
        prefer_shortcuts=prefer_shortcuts,
        shortcut_eval_always=shortcut_eval_always,
        apply_navmesh_validated_straighten=apply_navmesh_validated_straighten,
    )

    # Camera-only intermediate is only needed when both cost sources
    # are active and we want to attribute the delta separately.
    cam_only_route: Optional[ComposedRoute] = None
    if has_crowd and has_sound:
        cam_only_route = composer.compose(
            start_world,
            end_world,
            camera_area_costs=cam,
            sound_area_costs=None,
            via_points=via_points,
            enable_corridor_routing=enable_corridor_routing,
            corridor_section=corridor_section,
            enable_shortcuts=enable_shortcuts,
            prefer_shortcuts=prefer_shortcuts,
            shortcut_eval_always=shortcut_eval_always,
            apply_navmesh_validated_straighten=apply_navmesh_validated_straighten,
        )

    # Actual route (with all costs). When neither cost source is
    # active we can reuse base — saves a redundant compose.
    if not has_crowd and not has_sound:
        actual_route = base_route
    else:
        actual_route = composer.compose(
            start_world,
            end_world,
            camera_area_costs=cam if has_crowd else None,
            sound_area_costs=snd if has_sound else None,
            via_points=via_points,
            enable_corridor_routing=enable_corridor_routing,
            corridor_section=corridor_section,
            enable_shortcuts=enable_shortcuts,
            prefer_shortcuts=prefer_shortcuts,
            shortcut_eval_always=shortcut_eval_always,
            apply_navmesh_validated_straighten=apply_navmesh_validated_straighten,
        )

    # If the actual compose failed but the base succeeded, return the
    # base route and treat actual = base (UI shows no crowd/sound
    # contribution). Total failure → both None.
    primary = actual_route or base_route
    if primary is None:
        return None, None

    measure: Dict[str, Optional[float]] = {
        "distance_meters_base": None,
        "estimated_time_seconds_base": None,
        "distance_meters_actual": None,
        "estimated_time_seconds_actual": None,
        "distance_meters_crowd_delta": None,
        "estimated_time_seconds_crowd_delta": None,
        "distance_meters_sound_delta": None,
        "estimated_time_seconds_sound_delta": None,
    }

    if base_route is not None:
        measure["distance_meters_base"] = _route_distance_meters(base_route)
        measure["estimated_time_seconds_base"] = _route_time_seconds(
            base_route, speed_m_per_s=speed_m_per_s,
        )

    if actual_route is not None:
        measure["distance_meters_actual"] = _route_distance_meters(actual_route)
        measure["estimated_time_seconds_actual"] = _route_time_seconds(
            actual_route, speed_m_per_s=speed_m_per_s,
        )
    elif base_route is not None:
        measure["distance_meters_actual"] = measure["distance_meters_base"]
        measure["estimated_time_seconds_actual"] = measure["estimated_time_seconds_base"]

    base_d = measure["distance_meters_base"] or 0.0
    base_t = measure["estimated_time_seconds_base"] or 0.0
    actual_d = measure["distance_meters_actual"] or base_d
    actual_t = measure["estimated_time_seconds_actual"] or base_t

    # Force actual = base when no costs are active so NavMesh query
    # nondeterminism (tiny distance differences between compose runs)
    # doesn't cause a phantom "+0.1 s due to crowd" pill. Mirrors the
    # legacy compute_route_measure heuristic.
    if not has_crowd and not has_sound:
        measure["distance_meters_actual"] = base_d
        measure["estimated_time_seconds_actual"] = base_t
        actual_d = base_d
        actual_t = base_t

    if has_crowd and has_sound and cam_only_route is not None:
        cam_only_d = _route_distance_meters(cam_only_route)
        cam_only_t = _route_time_seconds(cam_only_route, speed_m_per_s=speed_m_per_s)
        measure["distance_meters_crowd_delta"] = max(0.0, cam_only_d - base_d)
        measure["estimated_time_seconds_crowd_delta"] = max(0.0, cam_only_t - base_t)
        measure["distance_meters_sound_delta"] = max(0.0, actual_d - cam_only_d)
        measure["estimated_time_seconds_sound_delta"] = max(0.0, actual_t - cam_only_t)
    elif has_crowd and not has_sound:
        measure["distance_meters_crowd_delta"] = max(0.0, actual_d - base_d)
        measure["estimated_time_seconds_crowd_delta"] = max(0.0, actual_t - base_t)
        measure["distance_meters_sound_delta"] = 0.0
        measure["estimated_time_seconds_sound_delta"] = 0.0
    elif has_sound and not has_crowd:
        measure["distance_meters_crowd_delta"] = 0.0
        measure["estimated_time_seconds_crowd_delta"] = 0.0
        measure["distance_meters_sound_delta"] = max(0.0, actual_d - base_d)
        measure["estimated_time_seconds_sound_delta"] = max(0.0, actual_t - base_t)

    return primary, measure


__all__ = [
    "compose_with_measure",
]
