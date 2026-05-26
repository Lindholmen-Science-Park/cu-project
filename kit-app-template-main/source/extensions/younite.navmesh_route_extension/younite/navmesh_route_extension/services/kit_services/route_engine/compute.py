"""Synchronous path computation for non-player routes."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ....scripts.navmesh_shortest_path import draw_path_curve, smooth_path_xz
from ..route_composer import compose_with_measure, get_route_composer
from ..route_measure import DEFAULT_WALK_SPEED_M_PER_S, RouteMeasure
from .constants import ENABLE_VALIDATED_STRAIGHTEN_CALCULATED_ROUTES
from .types import Vec3


class RouteInstanceComputeMixin:
    """Composer-driven `_compute_path` and measure wrapping."""

    def apply_precomputed_path(
        self,
        points: List[Vec3],
        measure: Optional[RouteMeasure] = None,
        *,
        segment_speeds: Optional[List[float]] = None,
        segment_classes: Optional[List[str]] = None,
    ) -> Tuple[bool, List[Vec3], Optional[str], Optional[RouteMeasure]]:
        """Adopt a polyline from the POI-list cache without re-running pathfinding."""
        if len(points) < 2:
            return False, [], "cached path too short", None

        if self._cfg.draw_path:
            from pxr import Gf

            pts_gf = [Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in points]
            ok, draw_err = draw_path_curve(
                pts_gf,
                path_prim=self._cfg.path_prim,
                curve_width=self._cfg.curve_width,
            )
            if not ok:
                print(f"[NAVMESH_ROUTE:{self._cfg.route_id}] Draw failed: {draw_err}")

        self._last_path_points = list(points)
        self._sync_arrival_aabb_from_path()
        n_seg = max(0, len(points) - 1)
        if (
            segment_speeds
            and len(segment_speeds) == n_seg
        ):
            self._last_segment_speeds = list(segment_speeds)
        else:
            self._last_segment_speeds = []
        if (
            segment_classes
            and len(segment_classes) == n_seg
        ):
            self._last_segment_classes = list(segment_classes)
        else:
            self._last_segment_classes = []
        self._cache_positions()
        self._dirty = False
        return True, list(points), None, measure

    def _compute_path(self) -> Tuple[bool, List[Vec3], Optional[str], Optional[RouteMeasure]]:
        """Single composer-driven path computation for every non-player route."""
        self._last_segment_speeds = []
        self._last_segment_classes = []

        start_t, end_t, err = self._resolve_endpoints()
        if err or start_t is None or end_t is None:
            return False, [], err or "endpoint resolve failed", None

        via_points: Optional[List[Vec3]] = None
        if self._cfg.via_points:
            via_points = self._prune_passed_via_points(
                start_t,
                list(self._cfg.via_points),
                end_t,
            )

        sec = getattr(self._cfg, "corridor_section", None)
        if (
            sec
            and str(self._cfg.route_id) == "seat_nav"
            and not via_points
            and end_t is not None
        ):
            try:
                from ..waypoint_router import plan_route

                pr = plan_route(
                    (float(start_t[0]), float(start_t[1]), float(start_t[2])),
                    (float(end_t[0]), float(end_t[1]), float(end_t[2])),
                    str(sec).strip(),
                    floor_hint_y=float(start_t[1]),
                    branch_join_pos=(
                        float(start_t[0]),
                        float(start_t[1]),
                        float(start_t[2]),
                    ),
                )
                if pr:
                    via_points = [(float(p[0]), float(p[1]), float(p[2])) for p in pr]
            except Exception:
                pass

        cam_costs = self._get_camera_area_costs() or {}
        snd_costs = self._get_sound_area_costs() or {}
        do_measure = self._get_route_measure_enabled()

        composer = get_route_composer()

        apply_validated = (
            ENABLE_VALIDATED_STRAIGHTEN_CALCULATED_ROUTES
            and not bool(via_points)
        )

        if do_measure:
            composed, measure_dict = compose_with_measure(
                composer,
                start_t,
                end_t,
                camera_area_costs=cam_costs if cam_costs else None,
                sound_area_costs=snd_costs if snd_costs else None,
                via_points=via_points,
                enable_corridor_routing=bool(self._cfg.use_composer),
                enable_shortcuts=bool(self._cfg.use_shortcuts),
                prefer_shortcuts=bool(self._cfg.prefer_shortcuts),
                shortcut_eval_always=bool(
                    getattr(self._cfg, "shortcut_eval_always", False)
                ),
                corridor_section=getattr(self._cfg, "corridor_section", None),
                speed_m_per_s=DEFAULT_WALK_SPEED_M_PER_S,
                apply_navmesh_validated_straighten=apply_validated,
            )
            if composed is None or len(composed.polyline) < 2:
                return False, [], "no walkable route", None
            measure = self._build_measure(measure_dict)
        else:
            composed = composer.compose(
                start_t,
                end_t,
                camera_area_costs=cam_costs if cam_costs else None,
                sound_area_costs=snd_costs if snd_costs else None,
                via_points=via_points,
                enable_corridor_routing=bool(self._cfg.use_composer),
                enable_shortcuts=bool(self._cfg.use_shortcuts),
                prefer_shortcuts=bool(self._cfg.prefer_shortcuts),
                shortcut_eval_always=bool(
                    getattr(self._cfg, "shortcut_eval_always", False)
                ),
                corridor_section=getattr(self._cfg, "corridor_section", None),
                apply_navmesh_validated_straighten=apply_validated,
            )
            if composed is None or len(composed.polyline) < 2:
                return False, [], "no walkable route", None
            measure = None

        points: List[Vec3] = [
            (float(p[0]), float(p[1]), float(p[2])) for p in composed.polyline
        ]
        if points and not composed.has_osm and not composed.has_shortcut and not via_points:
            points = smooth_path_xz(points)

        if self._cfg.draw_path and points:
            from pxr import Gf

            pts_gf = [Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in points]
            ok, draw_err = draw_path_curve(
                pts_gf,
                path_prim=self._cfg.path_prim,
                curve_width=self._cfg.curve_width,
            )
            if not ok:
                print(f"[NAVMESH_ROUTE:{self._cfg.route_id}] Draw failed: {draw_err}")

        self._last_path_points = points
        self._sync_arrival_aabb_from_path()
        self._last_segment_speeds = (
            list(composed.segment_speeds) if composed.segment_speeds else []
        )
        self._last_segment_classes = (
            list(composed.segment_classes) if composed.segment_classes else []
        )
        self._cache_positions()
        self._dirty = False
        return True, points, None, measure

    @staticmethod
    def _build_measure(measure_dict: Optional[Dict[str, Optional[float]]]) -> Optional[RouteMeasure]:
        """Convert :func:`compose_with_measure`'s dict into a ``RouteMeasure``."""
        if not measure_dict:
            return None
        return RouteMeasure(
            distance_meters_base=float(measure_dict.get("distance_meters_base") or 0.0),
            estimated_time_seconds_base=float(measure_dict.get("estimated_time_seconds_base") or 0.0),
            distance_meters_actual=measure_dict.get("distance_meters_actual"),
            estimated_time_seconds_actual=measure_dict.get("estimated_time_seconds_actual"),
            distance_meters_crowd_delta=measure_dict.get("distance_meters_crowd_delta"),
            estimated_time_seconds_crowd_delta=measure_dict.get("estimated_time_seconds_crowd_delta"),
            distance_meters_sound_delta=measure_dict.get("distance_meters_sound_delta"),
            estimated_time_seconds_sound_delta=measure_dict.get("estimated_time_seconds_sound_delta"),
        )
