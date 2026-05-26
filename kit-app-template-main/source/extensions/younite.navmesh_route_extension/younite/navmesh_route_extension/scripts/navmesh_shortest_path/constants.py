"""
Tunables for NavMesh path visualization, route-end flag, smoothing, and straightening.

Stage units are centimeters unless noted otherwise.
"""

# Path curve / waypoint group defaults (legacy API compat)
PATH_PRIM = "/World/ShortestPathCurve"
CURVE_WIDTH = 10.0

# Sphere waypoint visualization
SPHERE_RADIUS = 8.0
SPHERE_SPACING = 200.0
SPHERE_Y_OFFSET = 30.0
SPHERE_COLOR = (0.15, 0.95, 0.1)
SPHERE_EMISSIVE_INTENSITY = 4.0

# PreviewSurface fallback when ``flag.usd`` cannot be referenced (no MDL)
FLAG_FALLBACK_PREVIEW_DIFFUSE = (0.78, 0.82, 0.85)

# End-of-route marker (Kit viewport only; not bird-eye SVG)
ROUTE_END_FLAG_PRIM = "route_end_flag"
ROUTE_FLAG_MAT = "route_flag_mat"
ROUTE_END_FLAG_PLACEHOLDER_PRIM = "route_end_flag_placeholder"
ROUTE_END_FLAG_BAKED_PRIM_LEGACY = "route_end_flag_baked"
ROUTE_END_BEACON_PRIM = "route_end_beacon"

_FLAG_ASSET_PRIM = "/World"
# Scaled visual height (uniform scale = TARGET / native bbox Y). Do not increase this to “raise” the flag.
FLAG_ROUTE_END_TARGET_HEIGHT_CM = 100.0
# World-space: top of flag ≈ anchor.y + this (cm). Base Y = anchor.y + TOP − TARGET (asset origin at base).
FLAG_ROUTE_END_TOP_ABOVE_ANCHOR_CM = 200.0
FLAG_ROUTE_END_ROT_X_DEG = 0.0
FLAG_ROUTE_END_YAW_OFFSET_DEG = 180.0
FLAG_ROUTE_END_OFFSET_CM = 35.0

ROUTE_FLAG_FILENAMES = ("flag.usd", "flag.usdc")

# Laplacian smoothing (XZ only)
PATH_SMOOTH_ALPHA = 0.5
PATH_SMOOTH_ITERATIONS = 3
PATH_SMOOTH_MIN_POINTS = 4

# NavMesh-validated straightening
STRAIGHTEN_LENGTH_RATIO = 1.10
STRAIGHTEN_TIME_BUDGET_SEC = 0.15
PATHFIND_FAST_REJECT_XZ_CM = 400.0
STRAIGHTEN_SNAP_TOLERANCE_CM = 50.0
