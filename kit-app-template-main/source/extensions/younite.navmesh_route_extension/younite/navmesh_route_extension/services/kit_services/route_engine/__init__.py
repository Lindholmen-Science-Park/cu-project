"""
Route calculation engine — per-route state machine and configuration.

:class:`RouteConfig` and :class:`RouteInstance` are defined here; logic is split across
``route_engine/*.py`` (constants, types, compute, threaded player route, arrival, lifecycle).

All routes build polylines through :class:`route_composer.RouteComposer`; see
``route-composer.mdc`` for behaviour mapping.
"""

from __future__ import annotations

from .arrival import RouteInstanceArrivalMixin
from .compute import RouteInstanceComputeMixin
from .constants import ENABLE_VALIDATED_STRAIGHTEN_CALCULATED_ROUTES
from .helpers import _safe_prim_name
from .instance_base import RouteInstanceBase
from .player_route import RouteInstancePlayerMixin
from .types import RouteConfig, Vec3, Vec3Ref


class RouteInstance(
    RouteInstanceComputeMixin,
    RouteInstancePlayerMixin,
    RouteInstanceArrivalMixin,
    RouteInstanceBase,
):
    """Per-route state machine: async lifecycle, pathfinding, measurement, arrival."""

    pass


__all__ = [
    "ENABLE_VALIDATED_STRAIGHTEN_CALCULATED_ROUTES",
    "RouteConfig",
    "RouteInstance",
    "Vec3",
    "Vec3Ref",
    "_safe_prim_name",
]
