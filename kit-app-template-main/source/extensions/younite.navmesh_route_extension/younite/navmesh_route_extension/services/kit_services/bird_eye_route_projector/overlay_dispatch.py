"""Kit → web ``birdEyeRouteOverlay`` payload."""

from __future__ import annotations

from typing import Optional

from .resolution import get_renderer_resolution


def dispatch_bird_eye_route_overlay(
    points: list,
    osm_points: Optional[list] = None,
    pin_marker: Optional[dict] = None,
    start_marker: Optional[dict] = None,
    end_marker: Optional[dict] = None,
) -> None:
    try:
        from younite.messaging_core_extension.message_utils import dispatch_to_events2

        res = get_renderer_resolution()
        viewport = {"width": res[0], "height": res[1]} if res else None
        payload = {
            "points": points,
            "viewport": viewport,
        }
        if osm_points:
            payload["osmPoints"] = osm_points
        if pin_marker is not None:
            payload["pinMarker"] = pin_marker
        if start_marker is not None:
            payload["startMarker"] = start_marker
        if end_marker is not None:
            payload["endMarker"] = end_marker
        dispatch_to_events2("birdEyeRouteOverlay", payload)
    except Exception:
        pass
