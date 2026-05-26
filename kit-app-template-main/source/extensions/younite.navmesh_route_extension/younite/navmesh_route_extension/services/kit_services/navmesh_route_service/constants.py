"""Route IDs and defaults shared by NavMeshRouteService."""

# Routes that get a turn-by-turn guide for the web UI.
NAV_GUIDE_ROUTE_IDS = frozenset({"seat_nav", "exit_nav", "poi_nav", "quiet_zone_nav"})

# Routes that opt into shortcut routing (elevators, future bus stops,
# tunnels, …) when shortcuts are active. Player point-and-click
# never uses shortcuts — a click on the floor must produce a direct
# walk to that floor, not a detour through an elevator. Bird-eye and
# default routes are excluded for the same reason: previews / non-
# guided walks should not silently insert teleports.
SHORTCUT_ROUTE_IDS = frozenset({"seat_nav", "exit_nav", "poi_nav", "quiet_zone_nav"})

NAV_GUIDE_DESTINATION_KIND = {
    "seat_nav": "seat",
    "exit_nav": "exit",
    "poi_nav": "poi",
    "quiet_zone_nav": "quiet_zone",
}

# Default camera area traffic costs: light=1.0, medium=5, heavy=10+
DEFAULT_CAMERA_AREA_COSTS = {"cctv1_navmesh_area": 1.0}
