"""Constants and static graph data for corridor waypoint routing."""
from __future__ import annotations

from typing import Dict, List, Set

# Waypoints closer than this to the player are skipped (stage units = cm).
SKIP_THRESHOLD_CM = 200.0

# Default "you've reached this waypoint" radius used by
# :func:`prune_passed_via_points` for the head-of-list short-circuit.
# Matches the historical ``VIA_POINT_REACHED_CM`` constant the route
# engine has always used; lifted here so the composer's auto-corridor
# branch shares the same semantics.
VIA_POINT_REACHED_CM = 300.0

# Prefix used to auto-detect entrance waypoints (excluded from ring).
ENTRANCE_PREFIX = "nav_waypoint_entrance_"

# Upper-level sections: ordered branch chain from main corridor to section.
# All names listed here are excluded from the corridor ring.
UPPER_SECTION_BRANCH: Dict[str, List[str]] = {
    "E": ["nav_waypoint_DEF", "nav_waypoint_DEF_2", "nav_waypoint_DE_1", "nav_waypoint_E"],
    "F": ["nav_waypoint_DEF", "nav_waypoint_DEF_2", "nav_waypoint_DF_1", "nav_waypoint_F"],
    "H": ["nav_waypoint_GH", "nav_waypoint_GH_2", "nav_waypoint_GH_3", "nav_waypoint_H"],
    "P": ["nav_waypoint_OP", "nav_waypoint_OP_2", "nav_waypoint_OP_3", "nav_waypoint_P"],
    "S": ["nav_waypoint_RS", "nav_waypoint_RS_2", "nav_waypoint_RS_3", "nav_waypoint_S"],
}

# Branch waypoint names excluded from the corridor ring (static).
BRANCH_OFF_RING: Set[str] = set()
for _chain in UPPER_SECTION_BRANCH.values():
    BRANCH_OFF_RING.update(_chain)

# When ``plan_route`` runs after a vertical move (elevator exit), skip
# staircase branch prims that sit clearly *below* the current floor so
# the path does not descend back to landings the player already passed.
DEFAULT_BRANCH_FLOOR_TOL_CM = 450.0

# If the elevator (or resume) position is within this 3D distance (cm) of
# the section anchor prim, treat the player as already at the corridor end
# and use that waypoint alone.
JOIN_AT_SECTION_ANCHOR_MAX_CM = 700.0

# How many nearby ring waypoints to evaluate when picking the start.
START_CANDIDATES = 5

# NavMesh walk / XZ straight-line ratio used to reject ring candidates that
# would pierce geometry.
WALL_CHECK_RATIO = 6.0

# Max NavMesh queries spent validating ring-start candidates (cap latency).
MAX_VALIDATION_QUERIES = 3
