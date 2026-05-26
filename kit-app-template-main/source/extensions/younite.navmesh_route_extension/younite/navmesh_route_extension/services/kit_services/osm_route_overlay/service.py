"""Dev-only OSM route overlay — event wiring and orchestration.

Geometry, USD authoring, spatial queries, and path planning live in sibling
modules under this package. See the original monolith docstring in git
history or ``osm-route-overlay.mdc`` for the full behaviour write-up.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    OSM_ROADS_PRIM,
    OSM_ROUTE_WALK_SPEED,
    OVERLAY_ROOT,
    SNAP_PROXIMITY_CM,
)
from .mesh import build_mesh_data, purge_overlay_prims, write_mesh
from .path_planning import (
    is_same_chain_as_player,
    plan_auto_advance_polyline,
    plan_visible_polyline,
)
from .player_pose import get_player_forward_xz, get_player_xyz
from .spatial_queries import closest_point_on_edge
from .subgraph import build_visible_subgraph


class OsmRouteOverlayService:
    def __init__(
        self,
        *,
        mode_cache: Any,
        navmesh_route_service: Any = None,
    ):
        self._mode_cache = mode_cache
        self._navmesh_route_service = navmesh_route_service
        self._subs: List[Any] = []
        self._visible = False
        self._road_snap = False
        self._osm_graph = None
        self._osm_roads_offset: Optional[Tuple[float, float, float]] = None
        self._last_built_mode: Optional[str] = None
        self._visible_node_pos: Dict[str, Tuple[float, float, float]] = {}
        self._visible_adj: Dict[str, List[Tuple[str, float]]] = {}
        self._direct_walk_active: bool = False
        self._player_attached: bool = False

    def is_overlay_visible(self) -> bool:
        return bool(self._visible)

    def start(self) -> None:
        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import (
                register_outbound_events,
            )

            register_outbound_events([
                "osmRouteOverlayStatus",
                "osmRouteOverlayAttached",
            ])

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _alias(name: str) -> None:
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass

            _alias("osmRouteOverlaySet")
            _alias("younite.osm_route_overlay.click")
            _alias("younite.navigation.requestPoint")
            _alias("navmeshModeSet")
            _alias("autoMoveStatus")
            _alias("osmRouteOverlayAutoMove")

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/osm_route_overlay/overlay_set",
                    event_name="osmRouteOverlaySet",
                    on_event=self._on_overlay_set,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/osm_route_overlay/click",
                    event_name="younite.osm_route_overlay.click",
                    on_event=self._on_osm_route_overlay_click,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/osm_route_overlay/mode_changed",
                    event_name="navmeshModeSet",
                    on_event=self._on_mode_changed,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/osm_route_overlay/auto_move_status",
                    event_name="autoMoveStatus",
                    on_event=self._on_auto_move_status,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/osm_route_overlay/route_auto_move",
                    event_name="osmRouteOverlayAutoMove",
                    on_event=self._on_route_auto_move,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/osm_route_overlay/nav_request",
                    event_name="younite.navigation.requestPoint",
                    on_event=self._on_nav_request,
                    order=0,
                )
            )
        except Exception as e:
            print(f"[osm_route_overlay] start failed: {e}")

    def stop(self) -> None:
        self._subs.clear()
        try:
            self._teardown_overlay()
        except Exception:
            pass
        self._visible = False

    def _on_overlay_set(self, evt: Any) -> None:
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            if "visible" in payload:
                self._visible = bool(payload.get("visible"))
            if "roadSnap" in payload:
                self._road_snap = bool(payload.get("roadSnap"))

            if self._visible:
                self._setup_overlay()
            else:
                self._teardown_overlay()
        except Exception as e:
            print(f"[osm_route_overlay] overlay set failed: {e}")

    def _on_auto_move_status(self, evt: Any) -> None:
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            rid = str(payload.get("routeId") or "")
            active = bool(payload.get("active"))
            if rid == "player" and not active:
                self._direct_walk_active = False
        except Exception:
            pass

    def _on_nav_request(self, evt: Any) -> None:
        self._set_attached(False)

    def _set_attached(self, value: bool) -> None:
        if bool(value) == bool(self._player_attached):
            return
        self._player_attached = bool(value)
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2(
                "osmRouteOverlayAttached",
                {"attached": bool(value)},
            )
            print(f"[osm_route_overlay] player attached={bool(value)}")
        except Exception as e:
            print(f"[osm_route_overlay] attached dispatch failed: {e}")

    def _on_route_auto_move(self, evt: Any) -> None:
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            action = str(payload.get("action") or "play").lower()

            if action == "stop":
                self._stop_player_auto_move()
                return

            if not self._visible:
                print("[osm_route_overlay] auto-move ignored: overlay not visible")
                return

            player_xyz = get_player_xyz()
            if player_xyz is None:
                print("[osm_route_overlay] auto-move ignored: no player pose")
                return

            forward_xz = get_player_forward_xz()
            if forward_xz is None:
                print("[osm_route_overlay] auto-move ignored: camera forward unavailable")
                return

            ox, _, oz = self._get_osm_roads_offset()
            polyline = plan_auto_advance_polyline(
                player_xyz,
                forward_xz,
                visible_adj=self._visible_adj,
                visible_node_pos=self._visible_node_pos,
                ox=ox,
                oz=oz,
            )
            if not polyline or len(polyline) < 2:
                print("[osm_route_overlay] auto-move: no forward path found")
                return

            self._dispatch_polyline_directly(polyline)
        except Exception as e:
            print(f"[osm_route_overlay] auto_move handler failed: {e}")

    def _stop_player_auto_move(self) -> None:
        self._direct_walk_active = False
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2(
                "navigationStateSet",
                {
                    "movementMode": "pointClick",
                    "autoMove": False,
                    "routeId": "player",
                    "endPos": None,
                    "endpointPath": None,
                    "drawPath": False,
                    "useComposer": False,
                },
            )
        except Exception as e:
            print(f"[osm_route_overlay] stop dispatch failed: {e}")
        self._stop_player_route_engine()

    def _on_mode_changed(self, _evt: Any) -> None:
        if not self._visible:
            return
        try:
            self._setup_overlay()
        except Exception as e:
            print(f"[osm_route_overlay] rebuild on mode change failed: {e}")

    def _setup_overlay(self) -> None:
        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            graph = self._ensure_osm_graph()
            if graph is None:
                self._dispatch_status(False, "OSM graph not loaded")
                return

            mode = self._active_osm_mode()
            ox, _, oz = self._get_osm_roads_offset()
            verts, face_counts, face_indices = build_mesh_data(graph, mode, ox, oz)
            if not verts:
                self._dispatch_status(False, "No walking edges to draw")
                return

            purge_overlay_prims(stage)
            write_mesh(stage, verts, face_counts, face_indices)
            self._visible_node_pos, self._visible_adj = build_visible_subgraph(graph, mode)
            self._last_built_mode = mode
            edge_count = sum(len(nbs) for nbs in self._visible_adj.values()) // 2
            print(
                f"[osm_route_overlay] visible subgraph built mode={mode} "
                f"nodes={len(self._visible_node_pos)} edges={edge_count}"
            )
            self._dispatch_status(True, "")
        except Exception as e:
            print(f"[osm_route_overlay] setup overlay failed: {e}")

    def _teardown_overlay(self) -> None:
        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            purge_overlay_prims(stage)
            self._last_built_mode = None
            self._visible_node_pos = {}
            self._visible_adj = {}
            self._set_attached(False)
        except Exception as e:
            print(f"[osm_route_overlay] teardown failed: {e}")

    def _on_osm_route_overlay_click(self, evt: Any) -> None:
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            world_in = payload.get("world")
            if not isinstance(world_in, dict):
                return
            try:
                wx = float(world_in.get("x"))
                wy = float(world_in.get("y"))
                wz = float(world_in.get("z"))
            except (TypeError, ValueError):
                return

            pick_path = str(payload.get("pickPrimPath") or "")
            on_route_hit = pick_path.startswith(OVERLAY_ROOT)
            target = (wx, wy, wz)
            snap_reason = "none"
            snap_to_route = False
            same_chain_noop = False
            ox, _, oz = self._get_osm_roads_offset()

            if self._road_snap:
                snapped = self._snap_off_navmesh(wx, wy, wz)
                if snapped is not None:
                    target = snapped
                    snap_reason = "road_snap_dev"
                    snap_to_route = True
            elif on_route_hit:
                visible_hit = closest_point_on_edge(
                    wx,
                    wz,
                    graph=self._ensure_osm_graph(),
                    mode=self._active_osm_mode(),
                    ox=ox,
                    oz=oz,
                    visible_only=True,
                )
                if visible_hit is None:
                    snap_reason = "physx_route_no_edge"
                else:
                    target = (visible_hit[0], visible_hit[1], visible_hit[2])
                    player_xyz = get_player_xyz()
                    if (
                        self._player_attached
                        and player_xyz is not None
                        and is_same_chain_as_player(
                            player_xyz,
                            target,
                            visible_adj=self._visible_adj,
                            visible_node_pos=self._visible_node_pos,
                            ox=ox,
                            oz=oz,
                        )
                    ):
                        snap_reason = (
                            f"same_chain dist={visible_hit[3]:.0f}cm"
                            " (use Play to advance)"
                        )
                        same_chain_noop = True
                    else:
                        snap_reason = f"route_attach dist={visible_hit[3]:.0f}cm"
                        snap_to_route = True
            elif self._visible:
                from ..route_composer.types import NAVMESH_TOLERANCE_CM

                visible_hit = closest_point_on_edge(
                    wx,
                    wz,
                    graph=self._ensure_osm_graph(),
                    mode=self._active_osm_mode(),
                    ox=ox,
                    oz=oz,
                    visible_only=True,
                )
                nm_dist = self._distance_to_navmesh((wx, wy, wz))
                off_navmesh = nm_dist is None or nm_dist > float(NAVMESH_TOLERANCE_CM)

                if not off_navmesh:
                    nearest = visible_hit[3] if visible_hit is not None else -1
                    snap_reason = (
                        f"jump_off nearest={nearest:.0f}cm"
                        f" nm_dist={nm_dist:.0f}cm"
                    )
                else:
                    nm_label = (
                        f" nm_dist={nm_dist:.0f}cm"
                        if nm_dist is not None
                        else " nm_unknown"
                    )
                    if (
                        visible_hit is not None
                        and visible_hit[3] <= SNAP_PROXIMITY_CM
                    ):
                        target = (visible_hit[0], visible_hit[1], visible_hit[2])
                        snap_reason = f"near_route dist={visible_hit[3]:.0f}cm{nm_label}"
                        snap_to_route = True
                    else:
                        snapped = self._snap_off_navmesh(wx, wy, wz)
                        if snapped is not None:
                            target = snapped
                            snap_reason = (
                                f"off_navmesh{nm_label}"
                                f" tol={float(NAVMESH_TOLERANCE_CM):.0f}cm"
                            )
                            snap_to_route = True
                        else:
                            snap_reason = f"off_navmesh_no_osm{nm_label}"

            print(
                f"[osm_route_overlay] click world=({wx:.0f},{wy:.0f},{wz:.0f}) "
                f"prim={pick_path or '(none)'} "
                f"-> target=({target[0]:.0f},{target[1]:.0f},{target[2]:.0f})"
                f" snap={snap_reason}"
            )

            if same_chain_noop:
                return

            if snap_to_route:
                player_xyz = get_player_xyz()
                if player_xyz is not None:
                    polyline = plan_visible_polyline(
                        player_xyz,
                        target,
                        visible_adj=self._visible_adj,
                        visible_node_pos=self._visible_node_pos,
                        ox=ox,
                        oz=oz,
                    )
                    if polyline and len(polyline) >= 2:
                        if self._dispatch_polyline_directly(polyline):
                            return
                        print(
                            "[osm_route_overlay] direct dispatch failed,"
                            " falling back to NavMesh request"
                        )
                    else:
                        print(
                            "[osm_route_overlay] visible polyline planning"
                            " returned nothing, falling back to NavMesh request"
                        )
                else:
                    print(
                        "[osm_route_overlay] player position unavailable,"
                        " falling back to NavMesh request"
                    )

            self._direct_walk_active = False
            self._dispatch_nav_request(target, pick_path)
        except Exception as e:
            print(f"[osm_route_overlay] click handler failed: {e}")

    def _snap_off_navmesh(
        self, wx: float, wy: float, wz: float
    ) -> Optional[Tuple[float, float, float]]:
        ox, _, oz = self._get_osm_roads_offset()
        any_hit = closest_point_on_edge(
            wx,
            wz,
            graph=self._ensure_osm_graph(),
            mode=self._active_osm_mode(),
            ox=ox,
            oz=oz,
            visible_only=False,
        )
        if any_hit is None:
            return None
        return (any_hit[0], any_hit[1], any_hit[2])

    @staticmethod
    def _dispatch_nav_request(
        world: Tuple[float, float, float], pick_path: str
    ) -> None:
        try:
            import carb.eventdispatcher

            evt_payload = {
                "world": {
                    "x": float(world[0]),
                    "y": float(world[1]),
                    "z": float(world[2]),
                },
            }
            if pick_path:
                evt_payload["pickPrimPath"] = pick_path
            carb.eventdispatcher.get_eventdispatcher().dispatch_event(
                "younite.navigation.requestPoint",
                evt_payload,
            )
        except Exception as e:
            print(f"[osm_route_overlay] re-dispatch nav request failed: {e}")

    def _dispatch_status(self, ok: bool, error: str) -> None:
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2(
                "osmRouteOverlayStatus",
                {"success": ok, "error": error or None},
            )
        except Exception:
            pass

    def _active_osm_mode(self) -> str:
        cache = self._mode_cache
        if cache is None:
            return "walking"
        try:
            mode = cache.get_active_mode()
        except Exception:
            return "walking"
        return mode if mode in ("walking", "wheelchair") else "walking"

    def _ensure_osm_graph(self):
        if self._osm_graph is not None and getattr(self._osm_graph, "is_loaded", False):
            return self._osm_graph
        try:
            from younite.osm_navigation_extension.osm_graph_service import OsmGraphService

            if self._osm_graph is None:
                self._osm_graph = OsmGraphService()
            self._osm_graph.load()
            return self._osm_graph if self._osm_graph.is_loaded else None
        except Exception as e:
            print(f"[osm_route_overlay] OSM graph load failed: {e}")
            return None

    def _get_osm_roads_offset(self) -> Tuple[float, float, float]:
        if self._osm_roads_offset is not None:
            return self._osm_roads_offset
        try:
            import omni.usd
            from pxr import UsdGeom

            stage = omni.usd.get_context().get_stage()
            if stage:
                prim = stage.GetPrimAtPath(OSM_ROADS_PRIM)
                if prim and prim.IsValid():
                    xform = UsdGeom.Xformable(prim)
                    for op in xform.GetOrderedXformOps():
                        if op.GetOpName() == "xformOp:translate":
                            t = op.Get()
                            self._osm_roads_offset = (float(t[0]), float(t[1]), float(t[2]))
                            return self._osm_roads_offset
        except Exception:
            pass
        self._osm_roads_offset = (0.0, 0.0, 0.0)
        return self._osm_roads_offset

    def _stop_player_route_engine(self) -> None:
        svc = self._navmesh_route_service
        if svc is None:
            return
        try:
            svc.stop_route("player")
        except Exception as e:
            print(f"[osm_route_overlay] stop_route(player) failed: {e}")

    def _dispatch_polyline_directly(
        self, polyline: List[Tuple[float, float, float]]
    ) -> bool:
        if not polyline or len(polyline) < 2:
            return False

        self._stop_player_route_engine()

        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2
        except Exception as e:
            print(f"[osm_route_overlay] dispatch import failed: {e}")
            return False

        try:
            dispatch_to_events2(
                "navigationStateSet",
                {
                    "movementMode": "pointClick",
                    "autoMove": True,
                    "routeId": "player",
                    "endPos": None,
                    "endpointPath": None,
                    "drawPath": False,
                    "useComposer": False,
                },
            )
        except Exception as e:
            print(f"[osm_route_overlay] navigationStateSet prime failed: {e}")

        face_direction = not self._direct_walk_active

        seg_count = len(polyline) - 1
        payload = {
            "routeId": "player",
            "success": True,
            "points": [[p[0], p[1], p[2]] for p in polyline],
            "segmentSpeeds": [float(OSM_ROUTE_WALK_SPEED)] * seg_count,
            "segmentClasses": ["pedestrian"] * seg_count,
            "faceDirection": face_direction,
        }
        try:
            dispatch_to_events2("navmeshRouteWaypoints", payload)
            self._direct_walk_active = True
            self._set_attached(True)
            print(
                f"[osm_route_overlay] direct polyline dispatched"
                f" pts={len(polyline)} speed={float(OSM_ROUTE_WALK_SPEED):.1f}"
                f" face={face_direction}"
            )
            return True
        except Exception as e:
            print(f"[osm_route_overlay] dispatch_to_events2 failed: {e}")
            return False

    def _distance_to_navmesh(self, world: Tuple[float, float, float]) -> Optional[float]:
        cache = self._mode_cache
        if cache is None:
            return None
        try:
            nm = cache.get_active_navmesh()
        except Exception:
            return None
        if nm is None:
            return None
        try:
            import carb

            r = nm.query_closest_point(target=carb.Float3(world[0], world[1], world[2]))
            if r is None:
                return float("inf")
            cp, _ = r
            dx = float(cp.x) - world[0]
            dz = float(cp.z) - world[2]
            return math.sqrt(dx * dx + dz * dz)
        except Exception:
            return None
