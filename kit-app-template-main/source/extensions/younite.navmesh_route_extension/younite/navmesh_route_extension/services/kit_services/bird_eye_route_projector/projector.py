"""Bird's-eye route overlay projector — state, RDP, update loop, dispatch."""

from __future__ import annotations

import time
from typing import List, Optional

from .constants import RDP_EPSILON_CM, UPDATE_INTERVAL_MS
from .overlay_dispatch import dispatch_bird_eye_route_overlay
from .projection import project_waypoints_to_screen
from .types import Vec3


class BirdEyeRouteProjector:
    """Three-channel overlay: NavMesh polyline, OSM segment, pin + start/end anchors."""

    def __init__(self):
        self._waypoints: List[Vec3] = []
        self._osm_segment: List[Vec3] = []
        self._pin_marker_world: Optional[Vec3] = None
        self._start_world: Optional[Vec3] = None
        self._end_world: Optional[Vec3] = None
        self._last_sent_ms: float = 0
        self._update_sub = None

    def start(self):
        try:
            import omni.kit.app

            self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
                self._on_update, name="younite.navmesh_route_extension/birdEyeRouteUpdate"
            )
        except Exception as e:
            print(f"[bird_eye_route] update subscription failed: {e}")

    def shutdown(self):
        self._update_sub = None
        self._waypoints = []
        self._osm_segment = []
        self._pin_marker_world = None
        self._start_world = None
        self._end_world = None

    def set_pin_marker(self, world: Optional[Vec3]) -> None:
        if world is None:
            self._pin_marker_world = None
        else:
            self._pin_marker_world = (float(world[0]), float(world[1]), float(world[2]))
        self._last_sent_ms = 0

    def clear_pin_marker(self) -> None:
        self._pin_marker_world = None
        self._last_sent_ms = 0
        self._dispatch_if_empty()

    def set_route_endpoints(
        self,
        start_world: Optional[Vec3],
        end_world: Optional[Vec3],
    ) -> None:
        self._start_world = (
            (float(start_world[0]), float(start_world[1]), float(start_world[2]))
            if start_world is not None
            else None
        )
        self._end_world = (
            (float(end_world[0]), float(end_world[1]), float(end_world[2]))
            if end_world is not None
            else None
        )
        self._last_sent_ms = 0

    def clear_route_endpoints(self) -> None:
        self._start_world = None
        self._end_world = None
        self._last_sent_ms = 0
        self._dispatch_if_empty()

    def _dispatch_if_empty(self) -> None:
        if (
            not self._waypoints
            and not self._osm_segment
            and self._pin_marker_world is None
            and self._start_world is None
            and self._end_world is None
        ):
            dispatch_bird_eye_route_overlay([], [], None, None, None)

    def set_osm_segment(self, points_3d: List[Vec3]) -> None:
        if not points_3d:
            self._osm_segment = []
            return
        self._osm_segment = list(points_3d)
        self._last_sent_ms = 0

    def clear_osm_segment(self) -> None:
        self._osm_segment = []
        self._last_sent_ms = 0
        self._dispatch_if_empty()

    def on_route_computed(self, points_3d: List[Vec3]) -> None:
        if not points_3d or len(points_3d) < 2:
            self._waypoints = []
            return

        try:
            from ..navigation_guide import douglas_peucker_indices

            if len(points_3d) > 2:
                keep = douglas_peucker_indices(points_3d, RDP_EPSILON_CM)
                points_3d = [points_3d[i] for i in keep]

            self._waypoints = points_3d
            self._last_sent_ms = 0
        except Exception as e:
            print(f"[bird_eye_route] on_route_computed error: {e}")
            self._waypoints = []

    def clear_route(self):
        self._waypoints = []
        self._last_sent_ms = 0
        dispatch_bird_eye_route_overlay([], [], None, None, None)

    def _on_update(self, _event):
        if (
            not self._waypoints
            and not self._osm_segment
            and self._pin_marker_world is None
            and self._start_world is None
            and self._end_world is None
        ):
            return

        now_ms = time.monotonic() * 1000.0
        if (now_ms - self._last_sent_ms) < UPDATE_INTERVAL_MS:
            return

        try:
            import carb.settings

            vt = str(carb.settings.get_settings().get("/younite/camera/viewType") or "")
            if vt != "birdEye":
                return
        except Exception:
            return

        self._last_sent_ms = now_ms

        def _project_single(world: Optional[Vec3]) -> Optional[dict]:
            if world is None:
                return None
            proj = self._project_waypoints([world])
            return proj[0] if proj else None

        try:
            main_proj = self._project_waypoints(self._waypoints) if self._waypoints else []
            osm_proj = self._project_waypoints(self._osm_segment) if self._osm_segment else []
            pin_proj = _project_single(self._pin_marker_world)
            start_proj = _project_single(self._start_world)
            end_proj = _project_single(self._end_world)
            dispatch_bird_eye_route_overlay(
                main_proj or [],
                osm_proj or [],
                pin_proj,
                start_proj,
                end_proj,
            )
        except Exception:
            pass

    def _project_waypoints(self, source: Optional[List[Vec3]] = None) -> Optional[list]:
        points = source if source is not None else self._waypoints
        return project_waypoints_to_screen(points)
