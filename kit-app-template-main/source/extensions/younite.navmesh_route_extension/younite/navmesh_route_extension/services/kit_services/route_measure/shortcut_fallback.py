"""Shortcut-hop fallback when direct NavMesh measure fails (e.g. wheelchair + stairs)."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from ....scripts.navmesh_shortest_path import estimate_walk_time_seconds

from .constants import DEFAULT_WALK_SPEED_M_PER_S
from .types import RouteMeasure


def shortcut_fallback_measure(
    player_pos_t: Tuple[float, float, float],
    end_pos_t: Tuple[float, float, float],
    *,
    camera_area_costs: Optional[Dict[str, float]],
    sound_area_costs: Optional[Dict[str, float]],
    speed_m_per_s: float = DEFAULT_WALK_SPEED_M_PER_S,
) -> Optional[RouteMeasure]:
    """Try ``RouteComposer.compose(enable_shortcuts=True)``; return None if no route."""
    try:
        from ..route_composer.registry import get_route_composer
    except Exception:
        return None
    try:
        composer = get_route_composer()
    except Exception:
        return None
    if composer is None:
        return None
    try:
        composed = composer.compose(
            player_pos_t,
            end_pos_t,
            camera_area_costs=camera_area_costs,
            sound_area_costs=sound_area_costs,
            enable_shortcuts=True,
        )
    except Exception:
        return None
    if composed is None:
        return None
    distance_cm = float(getattr(composed, "distance_cm", 0.0) or 0.0)
    if distance_cm <= 0.0:
        return None
    distance_m = distance_cm / 100.0
    eta_s = estimate_walk_time_seconds(distance_cm, speed_m_per_s)
    return RouteMeasure(
        distance_meters_base=distance_m,
        estimated_time_seconds_base=eta_s,
        distance_meters_actual=distance_m,
        estimated_time_seconds_actual=eta_s,
    )
