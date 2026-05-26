"""
Route measurement service: distance and estimated time for navmesh paths.

Stable import path: ``from ...route_measure.route_measure_service import ...``
(or ``from ...route_measure import ...`` via the package ``__init__``).

Implementation is split across sibling modules in this package.
"""

from .compute_single import compute_route_measure
from .constants import DEFAULT_WALK_SPEED_M_PER_S
from .exits import compute_routes_to_exits
from .types import RouteMeasure, Vec3Ref

__all__ = [
    "DEFAULT_WALK_SPEED_M_PER_S",
    "RouteMeasure",
    "Vec3Ref",
    "compute_route_measure",
    "compute_routes_to_exits",
]
