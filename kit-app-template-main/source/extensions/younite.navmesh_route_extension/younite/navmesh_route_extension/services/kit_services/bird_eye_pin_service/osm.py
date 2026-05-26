"""Snap bird-eye clicks to the nearest reachable OSM graph node."""

from __future__ import annotations

from typing import Any, Optional, Tuple


class BirdEyePinOsmSnap:
    """Lazy OsmGraphService load + roads offset; mode follows NavMeshModeCache."""

    def __init__(self, mode_cache: Any):
        self._mode_cache = mode_cache
        self._osm_graph = None
        self._osm_roads_offset: Optional[Tuple[float, float, float]] = None

    def snap_click(
        self, click_world: Tuple[float, float, float]
    ) -> Optional[Tuple[float, float, float]]:
        """Snap world-space click to nearest *reachable* OSM node (main component, mode-aware).

        Returns node world position with roads offset applied, or ``None`` if the graph
        is unavailable. Preserves the node's authored Y so the flag sits on the road
        plane. Isolated subgraphs are excluded so "Get directions" cannot target a
        disconnected pocket.
        """
        graph = self._ensure_osm_graph()
        if graph is None:
            return None
        ox, _, oz = self._get_osm_roads_offset()
        mode = self._active_osm_mode()
        main = graph.main_component_id(mode) if hasattr(graph, "main_component_id") else None
        nid = graph.nearest_node(
            click_world[0] - ox,
            click_world[2] - oz,
            mode=mode,
            component=main,
        )
        if not nid:
            return None
        coords = graph.node_coords(nid)
        if not coords:
            return None
        nx, ny, nz = coords
        return (nx + ox, ny, nz + oz)

    def _active_osm_mode(self) -> str:
        cache = self._mode_cache
        if cache is None:
            return "walking"
        try:
            mode = cache.get_active_mode()
        except Exception:
            return "walking"
        if mode in ("walking", "wheelchair"):
            return mode
        return "walking"

    def _ensure_osm_graph(self):
        if self._osm_graph is not None and self._osm_graph.is_loaded:
            return self._osm_graph
        try:
            from younite.osm_navigation_extension.osm_graph_service import OsmGraphService

            if self._osm_graph is None:
                self._osm_graph = OsmGraphService()
            self._osm_graph.load()
            return self._osm_graph if self._osm_graph.is_loaded else None
        except Exception as e:
            print(f"[bird_eye_pin] OSM graph load failed: {e}")
            return None

    def _get_osm_roads_offset(self) -> Tuple[float, float, float]:
        if self._osm_roads_offset is not None:
            return self._osm_roads_offset
        try:
            import omni.usd
            from pxr import UsdGeom

            stage = omni.usd.get_context().get_stage()
            if stage:
                prim = stage.GetPrimAtPath("/World/OSM_Roads")
                if prim and prim.IsValid():
                    xform = UsdGeom.Xformable(prim)
                    for op in xform.GetOrderedXformOps():
                        if op.GetOpName() == "xformOp:translate":
                            t = op.Get()
                            self._osm_roads_offset = (
                                float(t[0]),
                                float(t[1]),
                                float(t[2]),
                            )
                            return self._osm_roads_offset
        except Exception:
            pass
        self._osm_roads_offset = (0.0, 0.0, 0.0)
        return self._osm_roads_offset
