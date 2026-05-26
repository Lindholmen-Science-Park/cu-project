"""NavMesh query_shortest_path pipeline — costs, snap validation, optional straightening."""

from __future__ import annotations

import math
import time
from typing import Callable, Dict, List, Optional, Tuple

import carb
import omni.usd
import omni.anim.navigation.core as nav

from .constants import (
    PATHFIND_FAST_REJECT_XZ_CM,
    STRAIGHTEN_LENGTH_RATIO,
    STRAIGHTEN_SNAP_TOLERANCE_CM,
    STRAIGHTEN_TIME_BUDGET_SEC,
)
from .path_metrics import path_length_cm
from .position_resolve import resolve_position
from .types import Vec3Ref


def _build_area_costs(inav, navmesh, camera_area_costs: Optional[Dict[str, float]] = None) -> list:
    """
    Build area_costs array for query_shortest_path.
    Uses camera_area_costs overrides for named areas; otherwise stage default costs.
    """
    area_count = navmesh.get_area_count()
    area_costs = []
    for i in range(area_count):
        area_name = navmesh.get_area_name(i)
        if camera_area_costs and area_name in camera_area_costs:
            area_costs.append(float(camera_area_costs[area_name]))
        else:
            try:
                default_cost = inav.get_area_default_cost(i)
                area_costs.append(float(default_cost))
            except Exception:
                area_costs.append(1.0)
    return area_costs


def _endpoint_snap_errors_navmesh(
    navmesh,
    start: carb.Float3,
    end: carb.Float3,
) -> Optional[str]:
    """If either endpoint is too far from the NavMesh in XZ, return error; else None."""
    tol_sq = PATHFIND_FAST_REJECT_XZ_CM * PATHFIND_FAST_REJECT_XZ_CM
    try:
        r_end = navmesh.query_closest_point(target=end)
        if r_end is None:
            return "No NavMesh near target — click closer to walkable ground."
        ce, _ = r_end
        dx = float(ce.x) - float(end.x)
        dz = float(ce.z) - float(end.z)
        if dx * dx + dz * dz > tol_sq:
            return "Target is too far from walkable NavMesh."
        r_start = navmesh.query_closest_point(target=start)
        if r_start is None:
            return "No NavMesh near start position."
        cs, _ = r_start
        dx = float(cs.x) - float(start.x)
        dz = float(cs.z) - float(start.z)
        if dx * dx + dz * dz > tol_sq:
            return "Start is too far from walkable NavMesh."
    except Exception:
        return None
    return None


def navmesh_path_length_cm(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    *,
    camera_area_costs: Optional[Dict[str, float]] = None,
    navmesh_override: Optional[object] = None,
) -> float:
    """Lightweight NavMesh distance query (no full ``calculate_path_points`` pipeline)."""
    try:
        inav = nav.acquire_interface()
        if not inav:
            return float("inf")
        if navmesh_override is not None:
            navmesh = navmesh_override
        else:
            navmesh = inav.get_navmesh()
        if not navmesh:
            return float("inf")

        s = carb.Float3(float(start[0]), float(start[1]), float(start[2]))
        e = carb.Float3(float(end[0]), float(end[1]), float(end[2]))

        if _endpoint_snap_errors_navmesh(navmesh, s, e):
            return float("inf")

        area_costs = _build_area_costs(inav, navmesh, camera_area_costs)

        try:
            path = navmesh.query_shortest_path(
                start_pos=s,
                end_pos=e,
                area_costs=area_costs if area_costs else [],
                straighten=True,
            )
        except Exception:
            return float("inf")
        if path is None or path.get_point_count() <= 1:
            return float("inf")
        return path_length_cm(path.get_points())
    except Exception:
        return float("inf")


def _is_segment_clear(
    navmesh,
    p_start,
    p_end,
    ratio_threshold: float = STRAIGHTEN_LENGTH_RATIO,
) -> bool:
    """True if NavMesh shortest path length ≈ straight-line (no obstacle detour)."""
    dx = float(p_end[0] - p_start[0])
    dy = float(p_end[1] - p_start[1])
    dz = float(p_end[2] - p_start[2])
    straight_dist = math.sqrt(dx * dx + dy * dy + dz * dz)

    if straight_dist < 1.0:
        return True

    try:
        start = carb.Float3(float(p_start[0]), float(p_start[1]), float(p_start[2]))
        end = carb.Float3(float(p_end[0]), float(p_end[1]), float(p_end[2]))
        path = navmesh.query_shortest_path(start_pos=start, end_pos=end, straighten=True)
        if path is None or path.get_point_count() <= 1:
            return False
        return (path.length() / straight_dist) <= ratio_threshold
    except Exception:
        return False


def _straighten_path(navmesh, points_gf: List) -> List:
    """Validated XZ straightening using NavMesh sub-queries (see module docstring in package)."""
    from pxr import Gf

    n = len(points_gf)
    if n < 3:
        return points_gf

    deadline = time.monotonic() + STRAIGHTEN_TIME_BUDGET_SEC

    keys: List[int] = [0]
    anchor = 0

    while anchor < n - 1:
        if time.monotonic() > deadline:
            return list(points_gf)
        best = anchor + 1
        for candidate in range(n - 1, anchor + 1, -1):
            if time.monotonic() > deadline:
                return list(points_gf)
            if _is_segment_clear(navmesh, points_gf[anchor], points_gf[candidate]):
                best = candidate
                break
        keys.append(best)
        anchor = best

    if keys[-1] != n - 1:
        keys.append(n - 1)

    result = list(points_gf)
    tol_sq = STRAIGHTEN_SNAP_TOLERANCE_CM * STRAIGHTEN_SNAP_TOLERANCE_CM

    for seg in range(len(keys) - 1):
        i_start = keys[seg]
        i_end = keys[seg + 1]
        if i_end - i_start <= 1:
            continue

        sx = float(points_gf[i_start][0])
        sz = float(points_gf[i_start][2])
        ex = float(points_gf[i_end][0])
        ez = float(points_gf[i_end][2])

        seg_dx = ex - sx
        seg_dz = ez - sz
        seg_sq = seg_dx * seg_dx + seg_dz * seg_dz

        if seg_sq < 1e-12:
            continue

        prev_t = 0.0
        for i in range(i_start + 1, i_end):
            px = float(points_gf[i][0])
            pz = float(points_gf[i][2])
            t = ((px - sx) * seg_dx + (pz - sz) * seg_dz) / seg_sq
            t = max(prev_t, min(1.0, t))
            prev_t = t
            new_x = float(sx + seg_dx * t)
            new_z = float(sz + seg_dz * t)
            orig_y = float(points_gf[i][1])

            try:
                probe = carb.Float3(new_x, orig_y, new_z)
                snap = navmesh.query_closest_point(target=probe)
                if snap is not None:
                    cp, _ = snap
                    dx2 = float(cp.x) - new_x
                    dz2 = float(cp.z) - new_z
                    if dx2 * dx2 + dz2 * dz2 > tol_sq:
                        continue
            except Exception:
                continue

            result[i] = Gf.Vec3f(new_x, orig_y, new_z)

    return result


def calculate_path_points(
    start_ref: Vec3Ref,
    end_ref: Vec3Ref,
    *,
    start_use_ground: bool = True,
    camera_area_costs: Optional[Dict[str, float]] = None,
    apply_navmesh_validated_straighten: bool = False,
    is_stale: Optional[Callable[[], bool]] = None,
    navmesh_override: Optional[object] = None,
) -> Tuple[bool, list, Optional[str]]:
    """
    Compute shortest-path polyline points (no drawing).

    Returns:
        (success, points as ``Gf.Vec3f`` list, error_message)
    """
    from pxr import Gf

    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if stage is None:
        return False, [], "No USD stage loaded. Open a scene first."

    try:
        start_pos = resolve_position(stage, start_ref, use_ground=start_use_ground)
    except Exception as e:
        return False, [], f"Failed to get start point position: {e}"

    try:
        end_pos = resolve_position(stage, end_ref, use_ground=False)
    except Exception as e:
        return False, [], f"Failed to get end point position: {e}"

    try:
        inav = nav.acquire_interface()
        if not inav:
            return False, [], "Failed to acquire navigation interface"

        if navmesh_override is not None:
            navmesh = navmesh_override
        else:
            try:
                if hasattr(inav, "is_navmesh_baking") and inav.is_navmesh_baking():
                    return False, [], "NavMesh is currently baking. Please wait a moment and try again."
            except Exception:
                pass

            navmesh = inav.get_navmesh()
            if not navmesh:
                return False, [], "No baked NavMesh available. Bake it first (Navigation UI)."
    except Exception as e:
        return False, [], f"NavMesh error: {e}"

    start = carb.Float3(float(start_pos[0]), float(start_pos[1]), float(start_pos[2]))
    end = carb.Float3(float(end_pos[0]), float(end_pos[1]), float(end_pos[2]))

    snap_err = _endpoint_snap_errors_navmesh(navmesh, start, end)
    if snap_err:
        return False, [], snap_err

    area_costs = _build_area_costs(inav, navmesh, camera_area_costs)

    if is_stale and is_stale():
        return False, [], "superseded"

    try:
        query_kwargs = dict(
            start_pos=start,
            end_pos=end,
            area_costs=area_costs if area_costs else [],
            straighten=True,
        )
        path = navmesh.query_shortest_path(**query_kwargs)
        if path is None:
            return False, [], "Path query returned None — start or end may be outside the NavMesh."
        count = path.get_point_count()
        if count <= 1:
            return (
                False,
                [],
                (
                    f"Path query returned {count} points. "
                    "Usually means start/end are not on/near the navmesh. "
                    "Make sure both points are on walkable surfaces within the NavMesh volume."
                ),
            )
        pts = path.get_points()
    except Exception as e:
        return False, [], f"Path query failed: {e}"

    points_gf = [Gf.Vec3f(p.x, p.y, p.z) for p in pts]

    if apply_navmesh_validated_straighten and len(points_gf) >= 3:
        try:
            points_gf = _straighten_path(navmesh, points_gf)
        except Exception:
            pass

    return True, points_gf, None
