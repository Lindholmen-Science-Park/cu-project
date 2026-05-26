"""
OSM leg planner — wraps :class:`OsmGraphService` for the composer.

Split out of :mod:`composer` so the composer file stays focused on the
A→B orchestration. Owns the cached ``OsmGraphService`` instance and
the ``/World/OSM_Roads`` translate offset (both reused across calls
to avoid reloading the city graph for every route compute).

Usage from inside the composer:

    self._osm = OsmLegPlanner(forward_bias_cm=500.0)
    osm_pts = self._osm.plan(start_world, end_world, ctx.is_stale, mode='walking')

Returns ``None`` on any failure (graph unavailable, endpoints in
disconnected sub-components, stale cancellation), or a tuple of
``(coords, edge_classes)`` where ``coords`` is the world-space polyline
vertex list and ``edge_classes`` is a parallel list of road-class
strings (``len(edge_classes) == len(coords) - 1``) — used for the
per-segment path-class tracking channel.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from .types import Vec3


OsmLegResult = Tuple[List[Vec3], List[str]]


class OsmLegPlanner:
    """Plan a single OSM leg between two world positions.

    Holds a singleton ``OsmGraphService`` instance + cached offset so
    the city graph is loaded once per process (the graph is large and
    the load is non-trivial).

    The forward-bias probe (``forward_bias_cm``) compensates for the
    ``nearest_node`` snap landing slightly behind the bridge relative
    to the destination — without the bias Dijkstra retraces a segment
    before turning forward, which shows as a 180° hook in the
    composed polyline.
    """

    def __init__(self, *, forward_bias_cm: float = 500.0):
        self._forward_bias_cm = float(forward_bias_cm)
        self._graph = None
        self._offset: Optional[Vec3] = None

    # ────────────────────────────────────────────────────────────
    # Lazy graph + offset accessors
    # ────────────────────────────────────────────────────────────

    def _ensure_graph(self):
        if self._graph is not None and getattr(self._graph, "is_loaded", False):
            return self._graph
        try:
            from younite.osm_navigation_extension.osm_graph_service import (
                OsmGraphService,
            )

            if self._graph is None:
                self._graph = OsmGraphService()
            self._graph.load()
            return self._graph if self._graph.is_loaded else None
        except Exception as exc:
            print(f"[route_composer.osm] graph load failed: {exc}")
            return None

    def _osm_roads_offset(self) -> Vec3:
        if self._offset is not None:
            return self._offset
        try:
            import omni.usd
            from pxr import UsdGeom

            stage = omni.usd.get_context().get_stage()
            if stage is not None:
                prim = stage.GetPrimAtPath("/World/OSM_Roads")
                if prim and prim.IsValid():
                    xform = UsdGeom.Xformable(prim)
                    for op in xform.GetOrderedXformOps():
                        if op.GetOpName() == "xformOp:translate":
                            t = op.Get()
                            self._offset = (
                                float(t[0]),
                                float(t[1]),
                                float(t[2]),
                            )
                            return self._offset
        except Exception:
            pass
        self._offset = (0.0, 0.0, 0.0)
        return self._offset

    # ────────────────────────────────────────────────────────────
    # Public planning entry point
    # ────────────────────────────────────────────────────────────

    def plan(
        self,
        start: Vec3,
        end: Vec3,
        is_stale: Optional[Callable[[], bool]] = None,
        *,
        mode: str = "walking",
    ) -> Optional[OsmLegResult]:
        """Plan an OSM polyline from ``start`` to ``end`` in world space.

        ``mode`` — ``"walking"`` / ``"wheelchair"`` / ``"car"``. Controls
        both ``nearest_node`` filtering (so a wheelchair never snaps to
        a stairs-only node) and the Dijkstra weighting.

        ``is_stale`` is checked before the (potentially slow) Dijkstra
        run — used by the player-route threading wrapper to bail out
        when a newer click has arrived.

        Returns ``(coords, edge_classes)`` where ``edge_classes`` has
        length ``len(coords) - 1`` (empty when ``len(coords) < 2``).
        """
        if is_stale is not None:
            try:
                if is_stale():
                    return None
            except Exception:
                pass

        graph = self._ensure_graph()
        if graph is None:
            return None
        ox, _, oz = self._osm_roads_offset()
        try:
            # Bias BOTH endpoint probes inward along the start→end
            # axis so `nearest_node` picks OSM nodes on the "forward"
            # side of each terminal. Mirror application avoids the
            # backtrack hook at either the navmesh→OSM or OSM→navmesh
            # handover.
            dx = end[0] - start[0]
            dz = end[2] - start[2]
            dist_se = (dx * dx + dz * dz) ** 0.5
            if dist_se > self._forward_bias_cm * 2.0:
                ux = dx / dist_se
                uz = dz / dist_se
                bias = self._forward_bias_cm
                sx = start[0] + ux * bias
                sz = start[2] + uz * bias
                ex = end[0] - ux * bias
                ez = end[2] - uz * bias
            else:
                sx, sz = start[0], start[2]
                ex, ez = end[0], end[2]
            sid = graph.nearest_node(sx - ox, sz - oz, mode=mode)
            eid = graph.nearest_node(ex - ox, ez - oz, mode=mode)
            if not sid or not eid:
                print(
                    f"[route_composer.osm] no nearest_node mode={mode} "
                    f"sid={sid} eid={eid} "
                    f"start=({sx:.0f},{sz:.0f}) end=({ex:.0f},{ez:.0f})"
                )
                return None
            # Same-node case: the player is already walking along an
            # OSM edge and clicked further along the same edge (or the
            # forward-bias projections both landed near the same node).
            # ``shortest_path(A, A)`` returns ``[A]`` with dist=0, which
            # the caller would otherwise reject as "no route". The
            # correct semantic is "stay on this OSM segment", so we
            # synthesise a degenerate 2-point polyline at the original
            # un-biased endpoints and let ``_osm_to_osm``'s stitching
            # bookend it with the player's exact start/end positions.
            if sid == eid:
                shifted: List[Vec3] = [
                    (float(start[0]), float(start[1]), float(start[2])),
                    (float(end[0]), float(end[1]), float(end[2])),
                ]
                return shifted, ["pedestrian"]
            path_ids, dist_cm = graph.shortest_path(sid, eid, mode=mode)
            # No component-fallback. The OSM data contains small,
            # isolated sub-graphs (e.g. a parking lot loop disconnected
            # from the main road network); if either endpoint falls
            # closest to one of those, an honest "no route" is the
            # right answer.
            if not path_ids or dist_cm <= 0.0:
                print(
                    f"[route_composer.osm] no shortest_path mode={mode} "
                    f"sid={sid} eid={eid} dist_cm={dist_cm}"
                )
                return None
            coords = graph.path_to_coords(path_ids)
            if not coords:
                return None
            edge_classes = graph.path_to_edge_classes(path_ids)
            shifted: List[Vec3] = [
                (float(x + ox), float(y), float(z + oz))
                for (x, y, z) in coords
            ]
            return shifted, edge_classes
        except Exception as exc:
            print(f"[route_composer.osm] plan failed: {exc}")
            return None


__all__ = ["OsmLegPlanner", "OsmLegResult"]
