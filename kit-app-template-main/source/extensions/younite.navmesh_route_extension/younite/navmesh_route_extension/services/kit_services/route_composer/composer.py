"""
:class:`RouteComposer` — unified A → B walkable path planning.

Given two world positions, compose a walkable route that can span
multiple NavMesh "islands" (independent walkable regions, e.g.
Scandinavium, Art Museum) and the OSM city graph between/around them.
Returns a single flat polyline + per-segment speed multipliers suitable
for the PointClickAutoMover, plus structured leg metadata for overlays.

Handles five cases:

    * same-island NavMesh → NavMesh
    * NavMesh → OSM            (inside start, outside end)
    * OSM → NavMesh            (outside start, inside end)
    * cross-island NavMesh → NavMesh   (via OSM bridge)
    * OSM → OSM                (both endpoints outside any island)

Single pathfinder for all routes:

    * The ``RouteEngine`` always calls ``compose()`` regardless of route
      type — point-and-click ``player`` routes, ``seat_nav``,
      ``find_toilets``, ``poi_nav``, etc. The composer accepts cost
      dicts (``camera_area_costs`` / ``sound_area_costs``), explicit
      ``via_points`` (for corridor-routed POI / seat flows) and an
      ``is_stale`` cancellation callback (for thread-cancelable player
      compute). All previous engine branches collapse to a single
      ``composer.compose(...)`` call.

Helpers live in sibling modules:

    * ``geometry`` — pure polyline / sampling helpers
    * ``types`` — data classes + tunables
    * ``osm`` — OSM graph + offset wrapper, OSM leg planner
    * ``measure`` — base / actual / crowd-delta / sound-delta breakdown
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from .geometry import (
    dedupe_close,
    is_segment_on_navmesh,
    trim_leading_backtrack,
    trim_trailing_backtrack,
    xz_dist2,
)
from .osm import OsmLegPlanner
from .types import (
    DEFAULT_ISLAND,
    ENTRANCE_PREFIX,
    NAVMESH_SEGMENT_SPEED,
    NAVMESH_TOLERANCE_CM,
    OSM_SEGMENT_SPEED,
    SHORTCUT_SEGMENT_SPEED,
    ComposedLeg,
    ComposedRoute,
    Vec3,
)


@dataclass
class _ComposeContext:
    """Per-call options bundle threaded through the case handlers.

    Created at the top of :meth:`RouteComposer.compose` so a single
    compose call's options propagate cleanly to every leg helper
    without polluting the public method signature with five kwargs
    each. Stays per-call (never stored on the composer) so concurrent
    composes from different threads/routes do not stomp on each
    other's state.
    """

    camera_area_costs: Optional[Dict[str, float]] = None
    sound_area_costs: Optional[Dict[str, float]] = None
    via_points: Optional[List[Vec3]] = None
    enable_corridor_routing: bool = False
    # Seat section letter for ``plan_route`` on shortcut outer legs.
    corridor_section: Optional[str] = None
    enable_shortcuts: bool = False
    # When True, the shortcut router returns the cheapest **valid** hop
    # regardless of direct walk length (prefer_shortcut semantics).
    # Vertical filters still gate validity. Only meaningful when
    # ``enable_shortcuts`` is also True.
    prefer_shortcuts: bool = False
    # When True (POI-list cache with shortcuts), always run the shortcut
    # router even when |ΔY| is below the same-tier cut and direct walking
    # succeeds — otherwise upstairs POIs never get compared to the lift.
    shortcut_eval_always: bool = False
    apply_navmesh_validated_straighten: bool = True
    is_stale: Optional[Callable[[], bool]] = None
    debug_log: bool = False
    # When False, :meth:`RouteComposer.compose` only plans pure NavMesh
    # routes on a single island — no ``NavMesh↔OSM`` hybrid legs, no
    # cross-island graph hops, and no lazy OSM graph load. Used for FP
    # ``player`` point-and-click unless bird-eye or the dev OSM overlay
    # is active.
    allow_osm_bridge: bool = True

    @property
    def merged_costs(self) -> Optional[Dict[str, float]]:
        """Camera + sound costs combined into one dict, or ``None``.

        ``calculate_path_points`` accepts a single ``camera_area_costs``
        kwarg; sound and crowd costs both end up in the same area-cost
        dictionary. Returning ``None`` (rather than an empty dict)
        lets the underlying call skip the cost-table build entirely.
        """
        if not self.camera_area_costs and not self.sound_area_costs:
            return None
        merged: Dict[str, float] = {}
        if self.camera_area_costs:
            merged.update(self.camera_area_costs)
        if self.sound_area_costs:
            merged.update(self.sound_area_costs)
        return merged or None

    def stale(self) -> bool:
        if self.is_stale is None:
            return False
        try:
            return bool(self.is_stale())
        except Exception:
            return False


# XZ tolerance (cm²) for matching a stitched-polyline point back to the
# raw OSM path to recover its edge class. 25 cm matches the dedupe_close
# floor — below that threshold dedupe would have collapsed the points.
_OSM_CLASS_MATCH_TOL2 = 25.0 * 25.0


def _osm_leg_classes(
    stitched: List[Vec3],
    raw_osm_pts: List[Vec3],
    raw_osm_classes: List[str],
) -> List[str]:
    """Return a class string for every segment in ``stitched``.

    Padding + trim + dedupe can insert synthetic endpoints (bridge /
    start / end) and drop interior ones; we recover each segment's
    class by looking its endpoints up in the original Dijkstra output.
    Synthetic edges — where either endpoint fails to match a raw OSM
    node — are tagged ``"bridge"`` so consumers can style the handover
    specially.
    """
    if len(stitched) < 2:
        return []
    # Build a small index of raw_osm_pts keyed by rounded (x, z) for
    # constant-time lookup. Fall back to linear scan if a miss.
    out: List[str] = []
    for a, b in zip(stitched, stitched[1:]):
        ia = _match_osm_index(a, raw_osm_pts)
        ib = _match_osm_index(b, raw_osm_pts)
        if ia is not None and ib is not None and ib == ia + 1 and ia < len(raw_osm_classes):
            out.append(raw_osm_classes[ia])
        else:
            out.append("bridge")
    return out


def _match_osm_index(p: Vec3, raw: List[Vec3]) -> Optional[int]:
    """Return the index of ``p`` in ``raw`` by XZ closeness, or None."""
    best_i = None
    best_d = _OSM_CLASS_MATCH_TOL2
    for i, q in enumerate(raw):
        d = xz_dist2(p, q)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


class RouteComposer:
    """Plan a walkable route between any two world positions.

    ``mode_cache`` is the NavMeshModeCache — passed so the composer
    queries the currently-active mode's mesh (walking vs wheelchair).
    Falls back to ``omni.anim.navigation.core.get_navmesh()`` when the
    cache is not attached.
    """

    # OSM entry-probe offset: when picking the OSM node to start the
    # path from, we probe a point this far (cm) forward of the bridge
    # toward the destination. `nearest_node` is pure Euclidean, so the
    # naive call at the bridge often snaps to a node slightly behind
    # the bridge relative to the pin — Dijkstra then has to retreat
    # one segment before turning forward, which shows as a 180° hook.
    _OSM_ENTRY_FORWARD_BIAS_CM = 500.0

    def __init__(self, *, mode_cache=None):
        self._mode_cache = mode_cache
        self._osm = OsmLegPlanner(forward_bias_cm=self._OSM_ENTRY_FORWARD_BIAS_CM)

    # ────────────────────────────────────────────────────────────
    # Mode resolution
    # ────────────────────────────────────────────────────────────

    def _active_osm_mode(self) -> str:
        """Return the OSM routing mode that should apply to this compose.

        Production CU flows automatically pick up the user's
        accessibility choice via :class:`NavMeshModeCache` — the same
        source of truth the dual-mode NavMesh uses. Falls back to
        ``"walking"`` when the cache is missing or returns an unknown
        mode string (so we never pass ``None`` into the OSM planner).
        """
        cache = self._mode_cache
        if cache is None:
            return "walking"
        try:
            mode = cache.get_active_mode()
        except Exception:
            return "walking"
        if mode in ("walking", "wheelchair", "car"):
            return mode
        return "walking"

    # ────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────

    def compose(
        self,
        start_world: Sequence[float],
        end_world: Sequence[float],
        *,
        camera_area_costs: Optional[Dict[str, float]] = None,
        sound_area_costs: Optional[Dict[str, float]] = None,
        via_points: Optional[Sequence[Sequence[float]]] = None,
        enable_corridor_routing: bool = False,
        corridor_section: Optional[str] = None,
        enable_shortcuts: bool = False,
        prefer_shortcuts: bool = False,
        shortcut_eval_always: bool = False,
        apply_navmesh_validated_straighten: bool = True,
        is_stale: Optional[Callable[[], bool]] = None,
        debug_log: bool = False,
        allow_osm_bridge: bool = True,
    ) -> Optional[ComposedRoute]:
        """Plan a walkable route from ``start_world`` to ``end_world``.

        All extra kwargs are optional and default to "no costs / no
        via-points / no cancellation" so legacy callers (
        ``composer.compose(start, end)``) continue to work unchanged.

        Args:
            camera_area_costs / sound_area_costs: NavMesh area cost
                overrides — passed through to ``calculate_path_points``
                via the merged ``camera_area_costs`` kwarg. Used by
                ``seat_nav`` / ``find_toilets`` / ``quiet_zone_nav`` so
                paths route around crowded camera areas and noisy
                quiet-zone areas.
            via_points: Explicit corridor via-points to walk through
                (start → via[0] → via[1] → … → end). Used when the
                caller has pre-computed a section-aware route (e.g.
                ``feature_commands_service`` for bird-eye seat
                directions or POI search).
            enable_corridor_routing: When True (and ``via_points`` is
                not supplied) and the route is intra-island, the
                composer asks ``waypoint_router.plan_route_to_position``
                for corridor via-points so the path follows the
                hand-placed entrance + ring waypoints instead of
                cutting across the bowl. Used by bird-eye / poi_nav
                routes; left False for player point-and-click so a
                click on the floor produces a direct path.
            apply_navmesh_validated_straighten: If False, skip the
                expensive O(n²) sub-query straightener — used for
                multi-segment via-point legs to keep latency bounded.
                Defaults to True (single-leg quality).
            is_stale: Callback invoked before each native NavMesh
                query. If it returns True the compose aborts and
                returns ``None``. Used by the player-route threading
                wrapper so a superseded click cancels mid-compose.
            debug_log: When True, route the composer's diagnostic
                ``[composer_dbg]`` prints. Off by default to keep
                periodic recalc logs quiet.
            allow_osm_bridge: When False, only same-island NavMesh legs
                are considered — no OSM graph, no cross-island hybrid
                routes. Intended for FP ``player`` clicks unless bird-eye
                or the dev "show OSM routes" overlay is active.
        """
        ctx = _ComposeContext(
            camera_area_costs=dict(camera_area_costs) if camera_area_costs else None,
            sound_area_costs=dict(sound_area_costs) if sound_area_costs else None,
            via_points=(
                [(float(p[0]), float(p[1]), float(p[2])) for p in via_points]
                if via_points
                else None
            ),
            enable_corridor_routing=bool(enable_corridor_routing),
            corridor_section=(
                (str(corridor_section).strip() or None)
                if corridor_section is not None
                else None
            ),
            enable_shortcuts=bool(enable_shortcuts),
            prefer_shortcuts=bool(prefer_shortcuts),
            shortcut_eval_always=bool(shortcut_eval_always),
            apply_navmesh_validated_straighten=bool(apply_navmesh_validated_straighten),
            is_stale=is_stale,
            debug_log=bool(debug_log),
            allow_osm_bridge=bool(allow_osm_bridge),
        )

        start = (
            float(start_world[0]),
            float(start_world[1]),
            float(start_world[2]),
        )
        end = (
            float(end_world[0]),
            float(end_world[1]),
            float(end_world[2]),
        )

        if ctx.stale():
            return None

        start_island = self._identify_island(start)
        end_island = self._identify_island(end)

        if ctx.debug_log:
            print(
                f"[composer_dbg] compose: start={start} island={start_island} "
                f"end={end} island={end_island}"
            )

        if ctx.stale():
            return None

        if ctx.enable_shortcuts:
            shortcut_route = self._try_shortcut_route(start, end, ctx)
            if shortcut_route is not None:
                print(
                    "[shortcut_router] route accepted "
                    f"(legs={len(shortcut_route.legs)}, "
                    f"polyline_distance_cm={shortcut_route.distance_cm:.0f})"
                )
                return shortcut_route
            # Failure path: find_best_plan already logged direct vs hop costs.

        # FP player policy: off-NavMesh pins must not eagerly load the OSM
        # graph or stitch bridge legs unless the UX explicitly opted into
        # city routing (bird-eye) or the dev route overlay.
        if not ctx.allow_osm_bridge:
            if start_island and end_island and start_island == end_island:
                r = self._same_navmesh(start, end, start_island, ctx)
                if ctx.debug_log:
                    if r is None:
                        print(
                            "[composer_dbg] compose (navmesh-only policy): "
                            f"same_island failed island={start_island}"
                        )
                    else:
                        print(
                            "[composer_dbg] compose (navmesh-only policy): "
                            f"ok legs={len(r.legs)} poly={len(r.polyline)}"
                        )
                elif r is None:
                    print(
                        "[composer] no route (navmesh-only policy, intra-island) "
                        f"island={start_island} "
                        f"start=({start[0]:.0f},{start[2]:.0f}) "
                        f"end=({end[0]:.0f},{end[2]:.0f})"
                    )
                else:
                    if ctx.debug_log:
                        print(
                            f"[composer_dbg] compose result: legs={len(r.legs)} "
                            f"polyline={len(r.polyline)} "
                            f"nm_pts={len(r.navmesh_points)} osm_pts={len(r.osm_points)}"
                        )
                return r
            if ctx.debug_log:
                print(
                    "[composer_dbg] compose: blocked OSM/hybrid branches "
                    f"(navmesh-only policy) start_island={start_island} "
                    f"end_island={end_island}"
                )
            else:
                print(
                    "[composer] no route: OSM bridge disabled for this call "
                    f"(start_island={start_island} end_island={end_island})"
                )
            return None

        if start_island and end_island:
            if start_island == end_island:
                variant = "same_navmesh"
                r = self._same_navmesh(start, end, start_island, ctx)
            else:
                variant = "cross_navmesh"
                r = self._cross_navmesh(start, end, start_island, end_island, ctx)
        elif start_island and not end_island:
            variant = "navmesh_to_osm"
            r = self._navmesh_to_osm(start, end, start_island, ctx)
        elif (not start_island) and end_island:
            variant = "osm_to_navmesh"
            r = self._osm_to_navmesh(start, end, end_island, ctx)
        else:
            variant = "osm_to_osm"
            r = self._osm_to_osm(start, end, ctx)

        if ctx.debug_log:
            if r is None:
                print(f"[composer_dbg] compose returned None variant={variant}")
            else:
                print(
                    f"[composer_dbg] compose result: legs={len(r.legs)} "
                    f"polyline={len(r.polyline)} "
                    f"nm_pts={len(r.navmesh_points)} osm_pts={len(r.osm_points)}"
                )
        # Always log the failure case at low volume so the next time
        # "no walkable route" hits the user we know which composer
        # branch failed (the most common cause is osm_to_osm finding
        # disconnected sub-graphs, which is otherwise invisible).
        elif r is None:
            print(
                f"[composer] no route variant={variant} "
                f"start_island={start_island} end_island={end_island} "
                f"start=({start[0]:.0f},{start[2]:.0f}) "
                f"end=({end[0]:.0f},{end[2]:.0f})"
            )
        return r

    # ────────────────────────────────────────────────────────────
    # Shortcut pre-pass
    # ────────────────────────────────────────────────────────────

    def _try_shortcut_route(
        self, start: Vec3, end: Vec3, ctx: _ComposeContext,
    ) -> Optional[ComposedRoute]:
        """Build a 3-leg ComposedRoute when a shortcut beats direct walking.

        Layout:

            * leg[0]: navmesh, start → entrance Xform
            * leg[1]: shortcut, [entrance, exit] (2 points)
            * leg[2]: navmesh, exit → end

        The router answers ``None`` whenever shortcuts are disabled,
        not configured, or no hop produces a lower Dijkstra cost than
        the direct walk — in those cases compose() falls through to
        the regular terrain-based handlers.
        """
        try:
            from ..shortcut_router import get_shortcut_router
        except Exception as exc:
            print(f"[shortcut_router] import failed: {exc}")
            return None
        router = get_shortcut_router()
        if router is None:
            print("[shortcut_router] singleton not registered")
            return None
        if not router.is_enabled():
            print("[shortcut_router] disabled — toggle 'Use shortcuts' first")
            return None
        try:
            groups = router.get_groups()
        except Exception as exc:
            print(f"[shortcut_router] get_groups failed: {exc}")
            return None
        if not groups:
            print("[shortcut_router] no groups loaded (check shortcuts.json + USD)")
            return None

        def _walk_len(a: Vec3, b: Vec3) -> Optional[float]:
            pts = self._navmesh_leg(a, b, ctx)
            if pts is None or len(pts) < 2:
                return None
            total = 0.0
            for i in range(1, len(pts)):
                p, q = pts[i - 1], pts[i]
                dx = p[0] - q[0]
                dz = p[2] - q[2]
                total += (dx * dx + dz * dz) ** 0.5
            return total

        # Same-floor skip: when |ΔY| is below the tier_cut threshold the
        # trip is "same-tier" and any shortcut would force an unnecessary
        # detour up/down a floor. In that case skipping the whole shortcut
        # pre-pass is a real perf win (saves the K NavMesh queries inside
        # ``find_best_plan``).
        #
        # Important: the optimisation is only safe when direct walking
        # actually succeeds. If walking is unreachable in the active mode
        # (classic case: wheelchair NavMesh blocks the staircase to the
        # lower-restaurant quiet zone, |ΔY| ~3 m so still under tier_cut),
        # the skip silently returns None and the caller has no fallback.
        # We probe direct walking once here; if it succeeds we trust the
        # tier optimisation and bail out, if it fails we fall through and
        # let ``find_best_plan`` try a vertical hop — its strict-shortest
        # comparison against ``direct_cm = _walk_len(...) = None`` makes
        # any feasible hop win, and the existing vertical filters still
        # reject illogical rides (basement-dip / wrong-band).
        #
        # Bypass the probe when ``prefer_shortcuts`` or ``shortcut_eval_always``
        # (POI-list cache) — we must compare lift vs walk for list sorting.
        if not ctx.prefer_shortcuts and not ctx.shortcut_eval_always:
            try:
                ys: List[float] = []
                for g in groups:
                    for n in g.nodes:
                        ys.append(float(n.pos[1]))
                if len(ys) >= 2:
                    ys_sorted = sorted(set(round(y, 1) for y in ys))
                    min_gap = min(
                        (ys_sorted[i + 1] - ys_sorted[i] for i in range(len(ys_sorted) - 1)),
                        default=0.0,
                    )
                    if min_gap > 0.0:
                        dy = abs(float(start[1]) - float(end[1]))
                        # Half the smallest lift landing gap alone can be too small
                        # when floors are dense — also require |ΔY| ≥ 750 cm so
                        # concourse → nearby section-A row stays out of the lift
                        # pre-pass.
                        tier_cut = max(float(min_gap) * 0.5, 750.0)
                        if dy < tier_cut and _walk_len(start, end) is not None:
                            return None
            except Exception:
                pass

        baseline_cm: Optional[float] = None
        if ctx.shortcut_eval_always and ctx.via_points:
            chain: List[Vec3] = [start] + list(ctx.via_points) + [end]
            corridor_total = 0.0
            corridor_ok = True
            for i in range(len(chain) - 1):
                leg_cm = _walk_len(chain[i], chain[i + 1])
                if leg_cm is None:
                    corridor_ok = False
                    break
                corridor_total += float(leg_cm)
            if corridor_ok:
                baseline_cm = corridor_total

        try:
            plan = router.find_best_plan(
                start, end, _walk_len,
                prefer_shortcut=ctx.prefer_shortcuts,
                corridor_section=ctx.corridor_section,
                baseline_cm=baseline_cm,
            )
        except Exception as exc:
            print(f"[route_composer] shortcut router failed: {exc}")
            return None
        if plan is None:
            return None

        # Re-run the navmesh legs to obtain the actual polylines (the
        # router only kept lengths). Corridor routing applies to each
        # outer leg when enabled on the compose context.
        in_island = self._identify_island(plan.hop.from_node.pos)
        out_island = self._identify_island(plan.hop.to_node.pos)
        leg_in = self._shortcut_navmesh_walk_polyline(
            start,
            plan.hop.from_node.pos,
            in_island,
            ctx,
            shortcut_walk_to_entrance=True,
        )
        if not leg_in:
            return None
        leg_out = self._shortcut_navmesh_walk_polyline(
            plan.hop.to_node.pos,
            end,
            out_island,
            ctx,
            post_elevator_floor_y=float(plan.hop.to_node.pos[1]),
        )
        if not leg_out:
            return None

        shortcut_leg = ComposedLeg(
            kind="shortcut",
            island=None,
            points=[plan.hop.from_node.pos, plan.hop.to_node.pos],
            shortcut_meta={
                "groupId": plan.hop.group_id,
                "type": plan.hop.type_,
                "fromPrimPath": plan.hop.from_node.prim_path,
                "toPrimPath": plan.hop.to_node.prim_path,
                "fromNodeId": plan.hop.from_node.node_id,
                "toNodeId": plan.hop.to_node.node_id,
                "fromLabel": plan.hop.from_node.label,
                "toLabel": plan.hop.to_node.label,
                "traversalSeconds": plan.hop.traversal_seconds,
            },
        )
        legs = [
            ComposedLeg("navmesh", in_island, leg_in),
            shortcut_leg,
            ComposedLeg("navmesh", out_island, leg_out),
        ]
        return self._finalize(legs, in_island, out_island)

    def _shortcut_leg_vias(
        self,
        a: Vec3,
        b: Vec3,
        ctx: _ComposeContext,
        *,
        shortcut_walk_to_entrance: bool = False,
        post_elevator_floor_y: Optional[float] = None,
    ) -> Optional[List[Vec3]]:
        """Corridor via-points for one NavMesh leg of a shortcut route.

        The walk **to** the shortcut entrance must not use ``plan_route``
        with a seat section — that would append the full upper-bowl
        staircase chain toward a lift that may sit on the ring/foyer.
        That leg uses ``plan_route_to_position`` whenever any corridor
        mode is active.

        The walk **from** the shortcut exit toward the real destination
        uses ``plan_route(player, seat, corridor_section)`` — the same
        function and section letter as non-shortcut ``seat_nav`` corridor
        routing.  ``floor_hint_y`` / ``branch_join_pos`` only adjust how
        much of ``UPPER_SECTION_BRANCH[section]`` is used after a vertical
        move; they never substitute a different graph.  If
        ``corridor_section`` is unset (typical for ``player`` / POI), this
        branch is not used.
        """
        if shortcut_walk_to_entrance:
            if not (
                ctx.corridor_section
                or ctx.via_points
                or ctx.enable_corridor_routing
            ):
                return None
            try:
                from ..waypoint_router import plan_route_to_position

                v = plan_route_to_position(
                    (float(a[0]), float(a[1]), float(a[2])),
                    (float(b[0]), float(b[1]), float(b[2])),
                )
            except Exception:
                return None
            return v if v else None

        sec = ctx.corridor_section
        if sec and str(sec).strip():
            try:
                from ..waypoint_router import plan_route

                join_xyz: Optional[Tuple[float, float, float]] = None
                if post_elevator_floor_y is not None:
                    join_xyz = (
                        float(a[0]),
                        float(a[1]),
                        float(a[2]),
                    )
                v = plan_route(
                    (float(a[0]), float(a[1]), float(a[2])),
                    (float(b[0]), float(b[1]), float(b[2])),
                    str(sec).strip(),
                    floor_hint_y=post_elevator_floor_y,
                    branch_join_pos=join_xyz,
                )
            except Exception:
                return None
            return v if v else None
        if ctx.via_points:
            try:
                from ..waypoint_router import plan_route_to_position

                v = plan_route_to_position(
                    (float(a[0]), float(a[1]), float(a[2])),
                    (float(b[0]), float(b[1]), float(b[2])),
                )
            except Exception:
                return None
            return v if v else None
        if ctx.enable_corridor_routing:
            v = self._plan_intra_island_via(a, b)
            return v if v else None
        return None

    def _shortcut_navmesh_walk_polyline(
        self,
        start: Vec3,
        end: Vec3,
        island: Optional[str],
        ctx: _ComposeContext,
        *,
        shortcut_walk_to_entrance: bool = False,
        post_elevator_floor_y: Optional[float] = None,
    ) -> Optional[List[Vec3]]:
        """NavMesh polyline for one shortcut outer leg (walk segment)."""
        isl = island or self._identify_island(start) or DEFAULT_ISLAND
        vias = self._shortcut_leg_vias(
            start,
            end,
            ctx,
            shortcut_walk_to_entrance=shortcut_walk_to_entrance,
            post_elevator_floor_y=post_elevator_floor_y,
        )
        if vias:
            r = self._build_multi_segment_navmesh_route(start, end, isl, vias, ctx)
            if r is not None and r.polyline and len(r.polyline) >= 2:
                return [
                    (float(p[0]), float(p[1]), float(p[2]))
                    for p in r.polyline
                ]
        return self._navmesh_leg(start, end, ctx)

    # ────────────────────────────────────────────────────────────
    # Island identification
    # ────────────────────────────────────────────────────────────

    def _identify_island(self, pos: Vec3) -> Optional[str]:
        """Return the island name a position belongs to, or ``None`` if OSM.

        Uses the nearest entrance waypoint to resolve the island once
        ``_is_on_navmesh`` confirms the point is walkable. Falls back
        to ``DEFAULT_ISLAND`` if entrances exist but are unnamed.
        """
        if not self._is_on_navmesh(pos):
            return None
        nearest = self._nearest_entrance(pos, island=None)
        if nearest is None:
            return DEFAULT_ISLAND
        island, _, _ = nearest
        return island

    def _is_on_navmesh(self, pos: Vec3) -> bool:
        navmesh = self._active_navmesh()
        if navmesh is None:
            # No mesh → treat everything as OSM so the composer falls
            # through to the OSM → OSM handler instead of silently
            # dropping the request.
            return False
        try:
            import carb

            target = carb.Float3(pos[0], pos[1], pos[2])
            result = navmesh.query_closest_point(target=target)
            if result is None:
                return False
            cp, _ = result
            dx = float(cp.x) - pos[0]
            dz = float(cp.z) - pos[2]
            d2 = dx * dx + dz * dz
            return d2 <= (NAVMESH_TOLERANCE_CM * NAVMESH_TOLERANCE_CM)
        except Exception:
            return False

    def _active_navmesh(self):
        """Return the best NavMesh handle available (cache preferred)."""
        if self._mode_cache is not None:
            try:
                nm = self._mode_cache.get_active_navmesh()
                if nm is not None:
                    return nm
            except Exception:
                pass
        try:
            import omni.anim.navigation.core as nav_mod

            inav = nav_mod.acquire_interface()
            return inav.get_navmesh() if inav else None
        except Exception:
            return None

    # ────────────────────────────────────────────────────────────
    # Entrance scanning
    # ────────────────────────────────────────────────────────────

    def _scan_entrances(self) -> List[Tuple[str, str, Vec3]]:
        """Return ``[(island, name, pos), ...]`` for every entrance.

        Entrance naming:
            * ``nav_waypoint_entrance_<island>_<idx>`` — modern form
            * ``nav_waypoint_entrance_<idx>`` — legacy, maps to
              ``DEFAULT_ISLAND`` so Scandinavium keeps working without
              renaming a single prim.
        """
        try:
            import omni.usd

            from ..waypoint_router import _scan_waypoints

            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return []
            wps = _scan_waypoints(stage)
        except Exception:
            return []

        out: List[Tuple[str, str, Vec3]] = []
        for name, pos in wps:
            if not name.startswith(ENTRANCE_PREFIX):
                continue
            rest = name[len(ENTRANCE_PREFIX):]
            parts = rest.rsplit("_", 1)
            if len(parts) == 2 and parts[0] and parts[1].isdigit():
                island = parts[0]
            else:
                island = DEFAULT_ISLAND
            out.append((island, name, pos))
        return out

    def _nearest_entrance(
        self, pos: Vec3, *, island: Optional[str],
    ) -> Optional[Tuple[str, str, Vec3]]:
        best: Optional[Tuple[str, str, Vec3]] = None
        best_d2 = float("inf")
        for item_island, name, epos in self._scan_entrances():
            if island is not None and item_island != island:
                continue
            d2 = xz_dist2(epos, pos)
            if d2 < best_d2:
                best_d2 = d2
                best = (item_island, name, epos)
        return best

    # ────────────────────────────────────────────────────────────
    # NavMesh ↔ OSM bridge selection
    # ────────────────────────────────────────────────────────────

    def _nearest_navmesh_point(self, pos: Vec3) -> Optional[Vec3]:
        """Query the NavMesh for the closest walkable surface point to ``pos``.

        Used as the bridge between NavMesh and OSM legs: for an
        outside-the-building pin, this naturally snaps to wherever the
        NavMesh reaches out to (a door opening, a side path, etc.),
        which is always a better handover point than a predefined
        entrance waypoint that might sit on the wrong side of the
        arena shell.

        Returns ``None`` if no NavMesh is loaded or the query fails;
        callers then fall back to :meth:`_nearest_entrance`.
        """
        navmesh = self._active_navmesh()
        if navmesh is None:
            return None
        try:
            import carb

            target = carb.Float3(pos[0], pos[1], pos[2])
            result = navmesh.query_closest_point(target=target)
            if result is None:
                return None
            cp, _ = result
            return (float(cp.x), float(cp.y), float(cp.z))
        except Exception:
            return None

    # When the player's NavMesh start position is at least this far (XZ,
    # cm) from every island entrance, we treat them as "outdoor city
    # walker" and prefer a direct NavMesh→OSM bridge near them over the
    # entrance handover. Players standing on a city sidewalk next to an
    # OSM route shouldn't have to backtrack to a stadium door before
    # bridging onto OSM. ~30 m comfortably clears the door-zone buffer
    # while still triggering entrance preference for anyone actually
    # inside or right at the door.
    _OUTDOOR_BRIDGE_DIST_CM = 3000.0

    def _candidate_bridges(
        self,
        outside_pos: Vec3,
        *,
        island: str,
        start_pos: Optional[Vec3] = None,
    ) -> List[Tuple[str, Vec3]]:
        """Bridge candidates (best-first) for NavMesh↔OSM handover.

        Order:
            1. (Optional) ``nm_closest_start`` — NavMesh point closest to
               ``start_pos`` when the player is far from any island
               entrance. This bypasses the "ran back to the main
               entrance" detour for outdoor city players who are
               already next to OSM.
            2. Every ``nav_waypoint_entrance_*`` for ``island``, sorted
               by proximity to ``outside_pos``. Hand-placed at real door
               openings — virtually always produce a corridor-respecting
               NavMesh leg.
            3. Nearest NavMesh surface point to ``outside_pos`` — fallback
               for islands without entrance waypoints. Validated against
               :meth:`_identify_island` to reject snaps onto a foreign
               island.

        ``start_pos`` is optional so legacy callers that don't pass it
        still get the original entrance-first ordering.
        """
        cands: List[Tuple[str, Vec3]] = []
        seen_pts: Set[Tuple[int, int, int]] = set()

        def _add(label: str, pt: Vec3) -> None:
            key = (
                int(round(pt[0])),
                int(round(pt[1])),
                int(round(pt[2])),
            )
            if key in seen_pts:
                return
            seen_pts.add(key)
            cands.append((label, pt))

        # 1. Outdoor-near-OSM optimisation: prepend ``nm_closest_start``
        # so the NavMesh leg is just a tiny hop onto the player's local
        # sidewalk instead of a long walk-back to a stadium door.
        if start_pos is not None:
            nearest_ent = self._nearest_entrance(start_pos, island=island)
            outdoor = nearest_ent is None
            if nearest_ent is not None:
                _, _, ent_pos = nearest_ent
                if xz_dist2(ent_pos, start_pos) > (
                    self._OUTDOOR_BRIDGE_DIST_CM * self._OUTDOOR_BRIDGE_DIST_CM
                ):
                    outdoor = True
            if outdoor:
                start_nm = self._nearest_navmesh_point(start_pos)
                if start_nm is not None:
                    pt_island = self._identify_island(start_nm)
                    if pt_island == island or pt_island is None:
                        _add("nm_closest_start", start_nm)

        # 2. Entrance waypoints (original behaviour).
        entrances: List[Tuple[float, str, Vec3]] = []
        for item_island, name, epos in self._scan_entrances():
            if item_island != island:
                continue
            d2 = xz_dist2(epos, outside_pos)
            entrances.append((d2, name, epos))
        entrances.sort(key=lambda t: t[0])
        for _, name, epos in entrances:
            _add(f"entrance:{name}", epos)

        # 3. nm_closest to target as the universal fallback.
        nm_pt = self._nearest_navmesh_point(outside_pos)
        if nm_pt is not None:
            pt_island = self._identify_island(nm_pt)
            if pt_island == island or pt_island is None:
                _add("nm_closest", nm_pt)

        return cands

    # ────────────────────────────────────────────────────────────
    # NavMesh leg
    # ────────────────────────────────────────────────────────────

    def _navmesh_leg(
        self, start: Vec3, end: Vec3, ctx: _ComposeContext,
    ) -> Optional[List[Vec3]]:
        """Compute a NavMesh polyline between two world positions.

        Threads ``ctx.merged_costs`` (camera + sound area cost dict)
        and ``ctx.is_stale`` into the underlying ``calculate_path_points``
        so the composer respects the same crowd / sound costs the
        legacy ``compute_route_measure`` flow used.
        """
        if ctx.stale():
            return None

        try:
            from ....scripts.navmesh_shortest_path import calculate_path_points
        except Exception as exc:
            print(f"[route_composer] navmesh import failed: {exc}")
            return None

        override = None
        if self._mode_cache is not None:
            try:
                override = self._mode_cache.get_active_navmesh()
            except Exception:
                override = None

        try:
            success, pts, _err = calculate_path_points(
                list(start),
                list(end),
                start_use_ground=False,
                camera_area_costs=ctx.merged_costs,
                apply_navmesh_validated_straighten=ctx.apply_navmesh_validated_straighten,
                is_stale=ctx.is_stale,
                navmesh_override=override,
            )
        except Exception:
            return None

        if not success or not pts:
            return None

        poly = [(float(p[0]), float(p[1]), float(p[2])) for p in pts]

        # Off-navmesh straight-line guard. The native pathfinder will
        # silently return a 2-point fallback polyline ``[start, end]``
        # when the endpoints fall on disconnected navmesh components.
        # Visually this shows up as a path that pierces straight through
        # walls to reach a bridge point on the other side. We sample the
        # segment and call ``query_closest_point`` on each sample: a real
        # walkable straight line stays within tolerance of the navmesh
        # the whole way; a fallback through walls measurably leaves it.
        if len(poly) == 2:
            try:
                navmesh_for_validate = override
                if navmesh_for_validate is None:
                    import omni.anim.navigation.core as nav_mod

                    inav = nav_mod.acquire_interface()
                    navmesh_for_validate = inav.get_navmesh() if inav else None
                if navmesh_for_validate is not None and not is_segment_on_navmesh(
                    navmesh_for_validate, poly[0], poly[1],
                ):
                    return None
            except Exception:
                # Validation must never break the happy path; on
                # failure assume the path is OK and continue.
                pass

        return poly

    # ────────────────────────────────────────────────────────────
    # Case handlers — one per start/end terrain combination
    # ────────────────────────────────────────────────────────────

    def _same_navmesh(
        self, start: Vec3, end: Vec3, island: str, ctx: _ComposeContext,
    ) -> Optional[ComposedRoute]:
        """Plan an intra-island NavMesh route.

        Via-point precedence:
            1. Caller-supplied ``ctx.via_points`` (e.g. POI search,
               bird-eye seat directions) take priority.
            2. When ``ctx.enable_corridor_routing`` is True, the
               corridor waypoint router
               (``waypoint_router.plan_route_to_position``) supplies
               via-points so the path follows the hand-placed
               entrance + ring waypoints. Bird-eye / ``poi_nav``
               flows opt in here so a within-arena pin doesn't cut
               across the bowl.
            3. Otherwise (player point-and-click, default route) the
               composer runs a single-leg validated pathfinder
               directly between ``start`` and ``end``.
        """
        via: Optional[List[Vec3]] = None
        if ctx.via_points:
            via = ctx.via_points
        elif ctx.enable_corridor_routing:
            auto = self._plan_intra_island_via(start, end)
            via = auto if auto else None

        if via:
            return self._build_multi_segment_navmesh_route(
                start, end, island, via, ctx,
            )

        pts = self._navmesh_leg(start, end, ctx)
        if pts is None:
            return None
        legs = [ComposedLeg("navmesh", island, pts)]
        return self._finalize(legs, island, island)

    def _plan_intra_island_via(
        self, start: Vec3, end: Vec3,
    ) -> List[Vec3]:
        """Waypoint-router via-points for an intra-island route, or ``[]``.

        Mirrors the engine's behaviour by pruning via-points the player
        has already walked past via the shared
        :func:`waypoint_router.prune_passed_via_points` helper. Without
        this pruning the bird-eye preview (which calls compose() directly
        and bypasses ``RouteInstance._compute_path``) would re-introduce
        ring waypoints the engine would otherwise drop, showing up as a
        spurious "extra arm" on the dashed overlay — most visible when
        the player is already inside the corridor and asks for directions
        to an outdoor map-marker spawn.
        """
        try:
            from ..waypoint_router import (
                plan_route_to_position,
                prune_passed_via_points,
            )
        except Exception:
            return []
        try:
            via = plan_route_to_position(
                (float(start[0]), float(start[1]), float(start[2])),
                (float(end[0]), float(end[1]), float(end[2])),
            )
        except Exception:
            return []
        if not via:
            return []
        normalised: List[Vec3] = [
            (float(p[0]), float(p[1]), float(p[2])) for p in via
        ]
        try:
            return prune_passed_via_points(
                (float(start[0]), float(start[1]), float(start[2])),
                normalised,
                (float(end[0]), float(end[1]), float(end[2])),
            )
        except Exception:
            return normalised

    def _build_multi_segment_navmesh_route(
        self,
        start: Vec3,
        end: Vec3,
        island: str,
        via: List[Vec3],
        ctx: _ComposeContext,
    ) -> Optional[ComposedRoute]:
        """Walk ``start → via[0] → via[1] → … → end`` via NavMesh legs.

        Each leg is individually pathfound by :meth:`_navmesh_leg` so
        crowd / sound costs apply per-segment. Multi-segment routes
        skip the expensive O(n²) validated straightener (the per-leg
        result is already corridor-bounded) — caller intent matches
        the old ``_compute_multi_segment`` behaviour.
        """
        # Multi-segment legs always use raw native straightening to
        # match the legacy `_compute_multi_segment` performance.
        # Override the ctx for these inner calls without mutating the
        # outer ctx (other code paths still want validated straight).
        seg_ctx = _ComposeContext(
            camera_area_costs=ctx.camera_area_costs,
            sound_area_costs=ctx.sound_area_costs,
            via_points=None,
            apply_navmesh_validated_straighten=False,
            is_stale=ctx.is_stale,
            debug_log=ctx.debug_log,
        )

        anchors: List[Vec3] = [start] + list(via) + [end]
        leg_points: List[List[Vec3]] = []
        for i in range(len(anchors) - 1):
            seg = self._navmesh_leg(anchors[i], anchors[i + 1], seg_ctx)
            if seg is None:
                # Fallback: try the raw single-leg pathfinder so the
                # caller still gets *something* rather than ``None``
                # (the user asked for a route, a possibly-imperfect
                # path is better than no path).
                pts = self._navmesh_leg(start, end, ctx)
                if pts is None:
                    return None
                return self._finalize(
                    [ComposedLeg("navmesh", island, pts)], island, island,
                )
            leg_points.append(seg)

        legs = [ComposedLeg("navmesh", island, pts) for pts in leg_points]
        return self._finalize(legs, island, island)

    def _navmesh_to_osm(
        self, start: Vec3, end: Vec3, start_island: str, ctx: _ComposeContext,
    ) -> Optional[ComposedRoute]:
        mode = self._active_osm_mode()
        for label, bridge in self._candidate_bridges(
            end, island=start_island, start_pos=start,
        ):
            nm = self._navmesh_leg(start, bridge, ctx)
            if nm is None:
                continue
            osm_res = self._osm.plan(bridge, end, ctx.is_stale, mode=mode)
            if osm_res is None:
                continue
            osm_pts, osm_classes = osm_res

            # Trim the OSM hook: `nearest_node(bridge)` can sit slightly
            # behind the bridge; Dijkstra starts by retreating before
            # turning toward `end`. Stitch: bridge (handover) → OSM
            # nodes → exact pin. ``_finalize`` drops the bridge vertex
            # as the shared leg boundary.
            osm_trimmed = trim_leading_backtrack(osm_pts, end)
            osm_stitched = dedupe_close([bridge] + osm_trimmed + [end])
            osm_leg_classes = _osm_leg_classes(
                osm_stitched, osm_pts, osm_classes,
            )
            legs = [
                ComposedLeg("navmesh", start_island, nm),
                ComposedLeg("osm", None, osm_stitched, osm_leg_classes),
            ]
            if ctx.debug_log:
                print(
                    f"[composer_dbg] navmesh→osm bridge={label} "
                    f"nm_pts={len(nm)} osm_pts={len(osm_stitched)}"
                )
            return self._finalize(legs, start_island, None)

        return None

    def _osm_to_navmesh(
        self, start: Vec3, end: Vec3, end_island: str, ctx: _ComposeContext,
    ) -> Optional[ComposedRoute]:
        mode = self._active_osm_mode()
        for label, bridge in self._candidate_bridges(
            start, island=end_island, start_pos=end,
        ):
            nm = self._navmesh_leg(bridge, end, ctx)
            if nm is None:
                continue
            osm_res = self._osm.plan(start, bridge, ctx.is_stale, mode=mode)
            if osm_res is None:
                continue
            osm_pts, osm_classes = osm_res

            osm_trimmed = trim_trailing_backtrack(osm_pts, bridge)
            osm_stitched = dedupe_close([start] + osm_trimmed + [bridge])
            osm_leg_classes = _osm_leg_classes(
                osm_stitched, osm_pts, osm_classes,
            )
            legs = [
                ComposedLeg("osm", None, osm_stitched, osm_leg_classes),
                ComposedLeg("navmesh", end_island, nm),
            ]
            return self._finalize(legs, None, end_island)

        return None

    def _cross_navmesh(
        self,
        start: Vec3,
        end: Vec3,
        start_island: str,
        end_island: str,
        ctx: _ComposeContext,
    ) -> Optional[ComposedRoute]:
        # Cross-island still needs an OSM connector on each side; we
        # stick with entrance waypoints because `query_closest_point`
        # on a multi-island mesh could snap onto the wrong island.
        mode = self._active_osm_mode()
        start_ent = self._nearest_entrance(start, island=start_island)
        end_ent = self._nearest_entrance(end, island=end_island)
        if start_ent is None or end_ent is None:
            return None
        _, _, se_pos = start_ent
        _, _, ee_pos = end_ent
        nm_start = self._navmesh_leg(start, se_pos, ctx)
        osm_res = self._osm.plan(se_pos, ee_pos, ctx.is_stale, mode=mode)
        nm_end = self._navmesh_leg(ee_pos, end, ctx)
        if nm_start is None or osm_res is None or nm_end is None:
            return None
        osm_pts, osm_classes = osm_res
        osm_leg_classes = _osm_leg_classes(osm_pts, osm_pts, osm_classes)
        legs = [
            ComposedLeg("navmesh", start_island, nm_start),
            ComposedLeg("osm", None, osm_pts, osm_leg_classes),
            ComposedLeg("navmesh", end_island, nm_end),
        ]
        return self._finalize(legs, start_island, end_island)

    def _osm_to_osm(
        self, start: Vec3, end: Vec3, ctx: _ComposeContext,
    ) -> Optional[ComposedRoute]:
        mode = self._active_osm_mode()
        osm_res = self._osm.plan(start, end, ctx.is_stale, mode=mode)
        if osm_res is None:
            return None
        osm_pts, osm_classes = osm_res
        # Pad the polyline with the exact player-start and pin-end
        # positions so the first/last auto-mover waypoint is at the
        # user's feet / chosen destination rather than on the nearest
        # OSM node.
        osm_stitched = dedupe_close([start] + osm_pts + [end])
        osm_leg_classes = _osm_leg_classes(osm_stitched, osm_pts, osm_classes)
        return self._finalize(
            [ComposedLeg("osm", None, osm_stitched, osm_leg_classes)],
            None,
            None,
        )

    # ────────────────────────────────────────────────────────────
    # Leg stitching / finalization
    # ────────────────────────────────────────────────────────────

    def _finalize(
        self,
        legs: List[ComposedLeg],
        start_island: Optional[str],
        end_island: Optional[str],
    ) -> ComposedRoute:
        polyline: List[Vec3] = []
        speeds: List[float] = []
        classes: List[str] = []
        prev_leg_kind: Optional[str] = None
        for i, leg in enumerate(legs):
            pts = leg.points
            if not pts:
                continue
            if i == 0:
                polyline.extend(pts)
            else:
                # Drop the shared boundary vertex between legs.
                polyline.extend(pts[1:])
            seg_count = max(0, len(pts) - 1)
            if leg.kind == "osm":
                speed = OSM_SEGMENT_SPEED
            elif leg.kind == "shortcut":
                speed = SHORTCUT_SEGMENT_SPEED
            else:
                speed = NAVMESH_SEGMENT_SPEED
            speeds.extend([speed] * seg_count)

            # Per-segment class. NavMesh legs emit a flat ``"navmesh"``
            # for every segment; OSM legs bring their own edge_classes
            # list (built in `_osm_leg_classes`). Cross-leg handover
            # segment (the first segment of a non-first leg) is the
            # one where the polyline crosses kinds — mark it ``"bridge"``
            # so listeners can fire transition affordances.
            leg_classes: List[str]
            if leg.kind == "navmesh":
                leg_classes = ["navmesh"] * seg_count
            elif leg.kind == "shortcut":
                leg_classes = ["shortcut"] * seg_count
            else:
                leg_classes = list(leg.edge_classes)[:seg_count]
                if len(leg_classes) < seg_count:
                    leg_classes.extend(
                        ["bridge"] * (seg_count - len(leg_classes))
                    )
            if i > 0 and prev_leg_kind != leg.kind and leg_classes:
                leg_classes[0] = "bridge"
            classes.extend(leg_classes)
            prev_leg_kind = leg.kind

        # Handover speed: the cross-kind segment inherits the *outgoing*
        # leg's speed (set by the extend loop above). An earlier version
        # retuned it down to NAVMESH_SEGMENT_SPEED "so the transition
        # feels continuous", but the bridge→first-OSM-node segment is
        # often 5-15 m long; walking it at 1× while every adjacent OSM
        # segment zipped by at 5× read as a hard stop. Leaving the
        # handover alone gives:
        #   navmesh → osm: bridge→O1 at OSM speed (matches OSM ahead)
        #   osm → navmesh: bridge→N1 at NavMesh speed (matches indoors)
        # — each transition inherits the speed of the terrain the
        # player is about to enter, which is what the user expects.

        # Defensive: if lengths desync (empty legs, one-point legs),
        # drop the speed table — the auto-mover then defaults to 1.0.
        expected_segs = max(0, len(polyline) - 1)
        if len(speeds) != expected_segs:
            speeds = []
        if len(classes) != expected_segs:
            # Fall back to a best-effort kind tag per segment; consumers
            # that need a perfectly-aligned table degrade gracefully.
            classes = []

        return ComposedRoute(
            legs=legs,
            polyline=polyline,
            segment_speeds=speeds,
            segment_classes=classes,
            start_island=start_island,
            end_island=end_island,
        )


__all__ = ["RouteComposer"]
