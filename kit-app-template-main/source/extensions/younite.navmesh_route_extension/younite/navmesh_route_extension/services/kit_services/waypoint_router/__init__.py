"""
Waypoint-guided corridor routing for arena navigation.

Three-tier graph:

* **Entrances** — auto-detected ``nav_waypoint_entrance_*`` prims outside
  the building.
* **Ring** — angular-sorted main-corridor waypoints.
* **Branches** — upper-level section chains via staircases (off-ring).

Implementation is split under ``waypoint_router/`` for readability; this
module re-exports the public surface unchanged for callers.
"""
from __future__ import annotations

from .cache import invalidate, scan_waypoints
from .config import UPPER_SECTION_BRANCH, VIA_POINT_REACHED_CM
from .geom import prune_passed_via_points
from .plan_to_position import plan_route_to_position
from .plan_to_seat import plan_route

# Historical private name used by bird_eye_pin_service.magnets / route_composer.
_scan_waypoints = scan_waypoints

__all__ = [
    "UPPER_SECTION_BRANCH",
    "VIA_POINT_REACHED_CM",
    "_scan_waypoints",
    "invalidate",
    "plan_route",
    "plan_route_to_position",
    "prune_passed_via_points",
]
