"""Route configuration dataclass and vector type aliases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple, Union

Vec3Ref = Union[str, Sequence[float]]
Vec3 = Tuple[float, float, float]


@dataclass
class RouteConfig:
    route_id: str
    start_ref: Vec3Ref
    end_ref: Vec3Ref
    start_use_ground: bool = True
    draw_path: bool = True
    path_prim: str = "/World/ShortestPathCurve"
    curve_width: float = 10.0
    enable_periodic_recalc: bool = True
    recalc_interval: float = 5.0
    position_recalc_threshold: float = 10.0
    via_points: List[Tuple[float, float, float]] = None  # type: ignore[assignment]
    # Callable returning the INavMesh handle this route should query (or None
    # for "use Kit's active navmesh"). Supplied by NavMeshRouteService so
    # wheelchair/walking POI meshes can be selected instantly per mode.
    get_navmesh_override: Optional[Callable[[], Optional[object]]] = None
    # Callable returning the active mode name ('walking' | 'wheelchair') for
    # logging only. Returns None if the mode cache isn't wired up.
    get_navmesh_mode: Optional[Callable[[], Optional[str]]] = None

    # When True the composer auto-picks corridor via-points for
    # intra-island routes (via ``waypoint_router.plan_route_to_position``)
    # when the caller doesn't supply ``via_points`` explicitly. Used by
    # bird-eye / ``poi_nav`` flows so a within-arena pin still walks
    # the entrance + ring corridor instead of cutting straight across
    # the bowl. Player / default routes leave this False so a click on
    # the floor produces the closest direct path. The orchestrator sets
    # this from the ``useComposer`` payload flag dispatched by
    # :mod:`feature_commands_service`.
    use_composer: bool = False

    # When True the composer runs the shortcut pre-pass (Dijkstra over
    # NavMesh + ``shortcuts.json`` graph) and may return a 3-leg route
    # (walk-to-entrance → shortcut hop → walk-from-exit). The
    # ``shortcut_traversal_service`` intercepts the resulting
    # ``"shortcut"`` path-class transition and runs a fade+teleport on
    # the player. Set per-route by ``NavMeshRouteService`` from the
    # ``_shortcuts_active`` flag (only guided routes — seat_nav,
    # exit_nav, poi_nav, quiet_zone_nav — opt in; player click/drag is
    # always direct walking).
    use_shortcuts: bool = False
    # When True (and ``use_shortcuts`` is True) the shortcut router
    # returns the cheapest **valid** hop regardless of direct walk
    # length — vertical filters still gate validity so basement-dip /
    # wrong-way hops are rejected. Wired from
    # ``NavMeshRouteService._prefer_shortcuts`` which the dev "Prefer
    # elevators" toggle sets. No effect when ``use_shortcuts`` is False.
    prefer_shortcuts: bool = False
    # Force shortcut router evaluation (bypass same-tier skip). Sticky on
    # POI-list cache activation so periodic recalc still compares lift vs
    # corridor walk (not only at list-build time).
    shortcut_eval_always: bool = False
    # Seat letter for ``waypoint_router.plan_route`` when rebuilding
    # corridor chains (shortcut outer legs, post-elevator resume with
    # empty ``via_points``). POI / exit routes leave this unset.
    corridor_section: Optional[str] = None

    def __post_init__(self):
        if self.via_points is None:
            self.via_points = []
