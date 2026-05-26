"""Tuning knobs and USD paths for the dev OSM route overlay."""

from typing import Set

OSM_ROADS_PRIM = "/World/OSM_Roads"
OVERLAY_ROOT = "/World/OsmRouteDevOverlay"
OVERLAY_MESH_PATH = f"{OVERLAY_ROOT}/Walking"
OVERLAY_MATERIAL_PATH = f"{OVERLAY_ROOT}/Looks/RouteMaterial"
OVERLAY_SHADER_PATH = f"{OVERLAY_MATERIAL_PATH}/Shader"

VISUAL_EDGE_CLASSES: Set[str] = {
    "pedestrian",
    "steps",
    "residential",
    "arterial",
    "service",
}

OVERLAY_HOVER_CM = 35.0
OVERLAY_WIDTH_CM = 110.0
OVERLAY_COLOR = (0.32, 0.62, 0.95)
OVERLAY_OPACITY = 0.22
OVERLAY_EMISSIVE_GAIN = 0.06
OVERLAY_ROUGHNESS = 0.18

SNAP_PROXIMITY_CM = 90.0
OSM_ROUTE_WALK_SPEED = 12.0
AT_JUNCTION_RADIUS_CM = 200.0
NEAR_ROUTE_RADIUS_CM = 250.0
MAX_AUTO_ADVANCE_HOPS = 64
