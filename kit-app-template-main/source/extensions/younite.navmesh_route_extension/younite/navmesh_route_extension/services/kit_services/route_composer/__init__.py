"""
Route composer — unified A → B walkable path planning.

Single pathfinder used by every route in the engine. The composer
handles same-island NavMesh, NavMesh ↔ OSM bridges, OSM ↔ OSM, and
cross-island NavMesh + OSM + NavMesh under one ``compose()`` call.
Cost dicts (``camera_area_costs`` / ``sound_area_costs``), via-points,
validated straightening, and stale cancellation are all surfaced as
keyword arguments — no separate "raw NavMesh" or "measure" code paths
in the route engine.

Public surface (re-exported from submodules):

* :class:`RouteComposer` — orchestrates ``compose()``
* :class:`ComposedLeg`, :class:`ComposedRoute` — result data types
* :func:`compose_with_measure` — base / actual / crowd-delta /
  sound-delta breakdown built on top of :class:`RouteComposer`
* :func:`set_route_composer` / :func:`get_route_composer` — cross-
  extension singleton access for the composer
* :func:`set_route_service` / :func:`get_route_service` — same, for
  the ``NavMeshRouteService`` preset installer

Internal layout:

* ``types`` — dataclasses + tunables (speeds, tolerances)
* ``geometry`` — pure polyline / sampling helpers
* ``osm`` — :class:`OsmLegPlanner` (city graph wrapper + Dijkstra)
* ``composer`` — the :class:`RouteComposer` class body
* ``measure`` — cost-aware base / actual / delta helper
* ``registry`` — singleton accessors
"""
from __future__ import annotations

from .composer import RouteComposer
from .measure import compose_with_measure
from .registry import (
    get_route_composer,
    get_route_service,
    set_route_composer,
    set_route_service,
)
from .types import (
    DEFAULT_ISLAND,
    DEFAULT_WALK_SPEED_M_PER_S,
    NAVMESH_SEGMENT_SPEED,
    NAVMESH_TOLERANCE_CM,
    OSM_SEGMENT_SPEED,
    SHORTCUT_SEGMENT_SPEED,
    ComposedLeg,
    ComposedRoute,
)


__all__ = [
    "ComposedLeg",
    "ComposedRoute",
    "RouteComposer",
    "NAVMESH_TOLERANCE_CM",
    "DEFAULT_ISLAND",
    "OSM_SEGMENT_SPEED",
    "NAVMESH_SEGMENT_SPEED",
    "SHORTCUT_SEGMENT_SPEED",
    "DEFAULT_WALK_SPEED_M_PER_S",
    "compose_with_measure",
    "set_route_composer",
    "get_route_composer",
    "set_route_service",
    "get_route_service",
]
