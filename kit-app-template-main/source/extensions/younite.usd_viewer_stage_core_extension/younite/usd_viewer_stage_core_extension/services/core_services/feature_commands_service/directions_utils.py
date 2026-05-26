"""
Pure helpers shared by the map-marker & seat directions flows.

Extracted from :class:`FeatureCommandsService` so the big async
handlers read as a sequence of intent-revealing calls
(``compose_route(...)``, ``yaw_from_polyline(...)``) instead of being
interleaved with 20-line USD / import blocks. No state, no ``self``.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence


def coerce_vec(raw) -> Optional[List[float]]:
    """Parse a vec3 from ``[x, y, z]`` or ``{"x":…, "y":…, "z":…}``.

    Shared between the synchronous event handler and the async worker
    so pin-anywhere / stored-FP / POI payloads all get normalised the
    same way.
    """
    if raw is None:
        return None
    try:
        if isinstance(raw, dict):
            return [float(raw.get("x")), float(raw.get("y")), float(raw.get("z"))]
        if isinstance(raw, (list, tuple)) and len(raw) >= 3:
            return [float(raw[0]), float(raw[1]), float(raw[2])]
    except (TypeError, ValueError):
        return None
    return None


def yaw_from_polyline(polyline: Sequence[Sequence[float]]) -> Optional[float]:
    """Degrees body yaw for the player to face along the first route segment.

    Walks the polyline from the start and returns the yaw of the first
    segment that advances more than 1 m (so a tiny leading wiggle
    doesn't produce a near-random facing).

    The first-person camera's local forward is ``-Z``; the player body
    yaw rotates about ``+Y``. For the camera (body's local -Z) to
    point toward ``(dx, dz)`` in world space, the body yaw must be
    ``atan2(-dx, -dz)`` — same convention used by
    ``navigation_orchestrator_service._face_route_direction`` when it
    smooth-rotates to face a freshly computed route. Using
    ``atan2(dx, dz)`` here (a previous attempt) would rotate the body
    the wrong way by 180°, which is exactly why users saw the camera
    pointing away from the route and had to turn around to find the
    path spheres.
    """
    if not polyline or len(polyline) < 2:
        return None

    MIN_SEG_CM = 100.0
    start = polyline[0]
    for p in polyline[1:]:
        dx = float(p[0]) - float(start[0])
        dz = float(p[2]) - float(start[2])
        if (dx * dx + dz * dz) < (MIN_SEG_CM * MIN_SEG_CM):
            continue
        return math.degrees(math.atan2(-dx, -dz))
    # Entire polyline is shorter than the threshold → fall back to
    # the final vertex direction so we at least aim at something.
    p = polyline[-1]
    dx = float(p[0]) - float(start[0])
    dz = float(p[2]) - float(start[2])
    if dx == 0.0 and dz == 0.0:
        return None
    return math.degrees(math.atan2(-dx, -dz))


def get_player_world_pos() -> Optional[List[float]]:
    """Return the player character's world-space XYZ, or ``None``."""
    try:
        import omni.usd
        from pxr import Usd, UsdGeom

        from ..world_conventions import PLAYER_CHARACTER_PATH

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return None
        prim = stage.GetPrimAtPath(PLAYER_CHARACTER_PATH)
        if not prim or not prim.IsValid():
            return None
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        m = cache.GetLocalToWorldTransform(prim)
        t = m.ExtractTranslation()
        return [float(t[0]), float(t[1]), float(t[2])]
    except Exception:
        return None


def resolve_prim_path_world(endpoint_path: str) -> Optional[List[float]]:
    """Resolve an arbitrary prim path to its world-space XYZ translation."""
    if not endpoint_path:
        return None
    try:
        import omni.usd
        from pxr import Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return None
        prim = stage.GetPrimAtPath(endpoint_path)
        if not prim or not prim.IsValid():
            return None
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        m = cache.GetLocalToWorldTransform(prim)
        t = m.ExtractTranslation()
        return [float(t[0]), float(t[1]), float(t[2])]
    except Exception:
        return None


def compose_route(start_world, end_world):
    """Wrap the shared RouteComposer singleton.

    Returns a ``ComposedRoute`` (from
    ``younite.navmesh_route_extension.services.kit_services.route_composer``)
    or ``None`` if no walkable path exists. The navmesh_route
    extension registers the mode-cache-aware composer on startup;
    a fallback is returned by ``get_route_composer`` if startup has
    not happened yet.
    """
    try:
        from younite.navmesh_route_extension.services.kit_services.route_composer import (
            get_route_composer,
        )
    except Exception as exc:
        print(f"[feature_commands] composer import failed: {exc}")
        return None
    try:
        composer = get_route_composer()
        # Same options bird-eye / poi_nav routes ultimately run with
        # in the route engine — keep the preview polyline aligned with
        # the polyline that the auto-mover will walk after "Start
        # Navigation".
        return composer.compose(
            start_world,
            end_world,
            enable_corridor_routing=True,
        )
    except Exception as exc:
        print(f"[feature_commands] composer failed: {exc}")
        return None


__all__ = [
    "coerce_vec",
    "yaw_from_polyline",
    "get_player_world_pos",
    "resolve_prim_path_world",
    "compose_route",
]
