"""Pin-marker and stale OSM preview cleanup on ``BirdEyeRouteProjector``."""

from __future__ import annotations

from typing import Any, Optional, Tuple


def push_pin_marker(
    route_projector: Any, world: Optional[Tuple[float, float, float]]
) -> None:
    if not route_projector:
        return
    try:
        route_projector.set_pin_marker(world)
    except Exception as e:
        print(f"[bird_eye_pin] push pin marker failed: {e}")


def clear_pin_overlay_state(route_projector: Any) -> None:
    """Clear solo pin marker and any lingering OSM preview segment."""
    if not route_projector:
        return
    try:
        route_projector.clear_pin_marker()
    except Exception:
        pass
    try:
        route_projector.clear_osm_segment()
    except Exception:
        pass
