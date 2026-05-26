"""
Route measurement: distance and estimated time for navmesh paths.

Import from this package (``from ...route_measure import RouteMeasure``) or from
:mod:`route_measure.route_measure_service` for the legacy module name.
"""

from .route_measure_service import (
    DEFAULT_WALK_SPEED_M_PER_S,
    RouteMeasure,
    Vec3Ref,
    compute_route_measure,
    compute_routes_to_exits,
)

__all__ = [
    "DEFAULT_WALK_SPEED_M_PER_S",
    "RouteMeasure",
    "Vec3Ref",
    "compute_route_measure",
    "compute_routes_to_exits",
]
