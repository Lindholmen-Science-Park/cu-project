"""
Process-wide singleton accessors for the route composer + navmesh route
service. Split from the composer itself so the cross-extension glue code
(feature_commands_service, bird-eye preview) can grab the active
services without pulling in the whole composer implementation.

``younite.navmesh_route_extension.extension`` registers both on
startup; ``feature_commands_service`` reads them at dispatch time.
"""
from __future__ import annotations

from typing import Any, Optional

from .composer import RouteComposer


_ROUTE_COMPOSER: Optional[RouteComposer] = None

# ``NavMeshRouteService`` singleton registered by the extension on
# startup. External callers (e.g. feature_commands_service) use this
# accessor to install composed preset routes without knowing the
# extension's internal layout. Typed as Any because the service lives
# in this same extension but the type is imported lazily to avoid a
# circular dependency at package import time.
_ROUTE_SERVICE: Optional[Any] = None


def set_route_composer(composer: Optional[RouteComposer]) -> None:
    global _ROUTE_COMPOSER
    _ROUTE_COMPOSER = composer


def get_route_composer() -> RouteComposer:
    """Return the registered composer, or a fresh fallback if none is set.

    A fallback (no ``mode_cache``) is returned if startup has not
    registered one yet — queries then fall back to the active NavMesh
    handle, which is fine for the single-mode case.
    """
    global _ROUTE_COMPOSER
    if _ROUTE_COMPOSER is None:
        _ROUTE_COMPOSER = RouteComposer()
    return _ROUTE_COMPOSER


def set_route_service(service: Optional[Any]) -> None:
    global _ROUTE_SERVICE
    _ROUTE_SERVICE = service


def get_route_service() -> Optional[Any]:
    return _ROUTE_SERVICE


__all__ = [
    "set_route_composer",
    "get_route_composer",
    "set_route_service",
    "get_route_service",
]
