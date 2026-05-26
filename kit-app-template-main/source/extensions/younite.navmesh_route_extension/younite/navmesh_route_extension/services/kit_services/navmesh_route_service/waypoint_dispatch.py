"""Events 2.0 dispatch for computed route waypoints, guide, and measure."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from younite.messaging_core_extension.message_utils import dispatch_to_events2

from ..route_measure import RouteMeasure
from .constants import NAV_GUIDE_DESTINATION_KIND, NAV_GUIDE_ROUTE_IDS


def dispatch_navmesh_route_waypoints(
    *,
    routes: Dict[str, Any],
    face_pending_routes: Set[str],
    route_id: str,
    success: bool,
    points: List[Tuple[float, float, float]],
    error: Optional[str],
    measure: Optional[RouteMeasure],
) -> None:
    """Publish waypoints to Events2; attach navigation guide and measure payloads."""
    rid = str(route_id)
    pts = points or []
    route_inst = routes.get(rid)
    if route_inst is not None:
        if rid == "seat_nav" and success and len(pts) >= 2:
            route_inst._seat_proximity_toast_sent = False
        route_inst.clear_navigation_runtime()
        if success and len(pts) >= 2 and rid in NAV_GUIDE_ROUTE_IDS:
            try:
                from ..navigation_guide import build_navigation_guide

                dest = NAV_GUIDE_DESTINATION_KIND.get(rid, "unknown")
                guide = build_navigation_guide(pts, dest)
                if guide:
                    route_inst.set_navigation_runtime(guide)
            except Exception:
                pass

    payload: Dict[str, Any] = {
        "routeId": route_id,
        "success": bool(success),
        "points": [[p[0], p[1], p[2]] for p in pts],
    }
    # Per-segment speed multipliers (preset routes only).
    if (
        success
        and route_inst is not None
        and route_inst._last_segment_speeds
        and len(route_inst._last_segment_speeds) == max(0, len(pts) - 1)
    ):
        payload["segmentSpeeds"] = list(route_inst._last_segment_speeds)
    # Per-segment path classes (parallel to segmentSpeeds).
    if (
        success
        and route_inst is not None
        and route_inst._last_segment_classes
        and len(route_inst._last_segment_classes) == max(0, len(pts) - 1)
    ):
        payload["segmentClasses"] = list(route_inst._last_segment_classes)
    bounds = route_inst.get_arrival_aabb_bounds() if (success and route_inst is not None) else None
    if bounds:
        mn, mx = bounds
        payload["arrivalAabbMin"] = [mn[0], mn[1], mn[2]]
        payload["arrivalAabbMax"] = [mx[0], mx[1], mx[2]]
    if error:
        payload["error"] = str(error)
    if success and route_id in face_pending_routes:
        face_pending_routes.discard(route_id)
        payload["faceDirection"] = True
    elif not success:
        face_pending_routes.discard(route_id)
    if measure is not None:
        payload["distanceMetersBase"] = measure.distance_meters_base
        payload["estimatedTimeSecondsBase"] = measure.estimated_time_seconds_base
        if measure.distance_meters_actual is not None:
            payload["distanceMetersActual"] = measure.distance_meters_actual
        if measure.estimated_time_seconds_actual is not None:
            payload["estimatedTimeSecondsActual"] = measure.estimated_time_seconds_actual
    try:
        dispatch_to_events2("navmeshRouteWaypoints", payload)
    except Exception:
        pass

    if route_inst is not None and route_inst._nav_guide_public and success:
        try:
            guide_payload: Dict[str, Any] = {
                "routeId": route_id,
                "success": True,
                **route_inst._nav_guide_public,
            }
            dispatch_to_events2("navmeshRouteGuide", guide_payload)
        except Exception:
            pass

    if measure is not None:
        try:
            measure_payload: Dict[str, Any] = {
                "routeId": route_id,
                "success": bool(success),
                "distanceMetersBase": measure.distance_meters_base,
                "estimatedTimeSecondsBase": measure.estimated_time_seconds_base,
            }
            if error:
                measure_payload["error"] = str(error)
            if measure.distance_meters_actual is not None:
                measure_payload["distanceMetersActual"] = measure.distance_meters_actual
            if measure.estimated_time_seconds_actual is not None:
                measure_payload["estimatedTimeSecondsActual"] = measure.estimated_time_seconds_actual
            if measure.distance_meters_crowd_delta is not None:
                measure_payload["distanceMetersCrowdDelta"] = measure.distance_meters_crowd_delta
            if measure.estimated_time_seconds_crowd_delta is not None:
                measure_payload["estimatedTimeSecondsCrowdDelta"] = measure.estimated_time_seconds_crowd_delta
            if measure.distance_meters_sound_delta is not None:
                measure_payload["distanceMetersSoundDelta"] = measure.distance_meters_sound_delta
            if measure.estimated_time_seconds_sound_delta is not None:
                measure_payload["estimatedTimeSecondsSoundDelta"] = measure.estimated_time_seconds_sound_delta
            if route_inst is not None:
                measure_payload.update(route_inst.navigation_measure_extras())
            dispatch_to_events2("navmeshRouteMeasure", measure_payload)
        except Exception:
            pass
