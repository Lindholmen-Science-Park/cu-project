"""
NavMesh shortest-path helpers — modular layout for pathfinding, metrics, and FP visualization.

Subpackages / modules
---------------------
``constants`` — Tunables (sphere spacing, straightening budgets, flag asset names).

``types`` — ``Vec3Ref`` (prim path, triple, or USD vec).

``position_resolve`` — Resolve prim paths / tuples to ``Gf.Vec3d`` world positions.

``path_metrics`` — Polyline length, walk-time estimate, Laplacian XZ smoothing.

``navmesh_pathfind`` — ``query_shortest_path`` pipeline: costs, snap checks,
validated straightening, ``calculate_path_points``.

``route_end_flag`` — Cached ``flag.usd`` geometry and end-of-route marker authoring.

``path_visualization`` — Session-layer waypoint spheres, ``draw_path_curve`` /
``remove_path_curve``, standalone ``calculate_path`` CLI helper.

Import surface (unchanged for callers)
--------------------------------------
::

    from ...scripts.navmesh_shortest_path import calculate_path_points, draw_path_curve, ...

"""

from .constants import (
    CURVE_WIDTH,
    PATH_PRIM,
)
from .navmesh_pathfind import calculate_path_points, navmesh_path_length_cm
from .path_metrics import estimate_walk_time_seconds, path_length_cm, smooth_path_xz
from .path_visualization import calculate_path, draw_path_curve, main, remove_path_curve
from .position_resolve import (
    get_ground_position,
    get_world_translation,
    resolve_position,
)
from .route_end_flag import set_route_flag_data_root
from .types import Vec3Ref

__all__ = [
    "CURVE_WIDTH",
    "PATH_PRIM",
    "Vec3Ref",
    "calculate_path",
    "calculate_path_points",
    "draw_path_curve",
    "estimate_walk_time_seconds",
    "get_ground_position",
    "get_world_translation",
    "main",
    "navmesh_path_length_cm",
    "path_length_cm",
    "remove_path_curve",
    "resolve_position",
    "set_route_flag_data_root",
    "smooth_path_xz",
]
