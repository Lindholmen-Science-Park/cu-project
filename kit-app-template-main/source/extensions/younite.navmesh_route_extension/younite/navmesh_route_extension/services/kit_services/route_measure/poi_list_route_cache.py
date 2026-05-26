"""In-memory cache of POI-list pathfinding results (restroom / quiet-zone bulk queries)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .types import RouteMeasure, Vec3Ref

Point = Tuple[float, float, float]
CacheEntry = Dict[str, object]

_CACHE: Dict[str, CacheEntry] = {}


def _player_key(player_ref: Vec3Ref) -> str:
    if isinstance(player_ref, str):
        return f"path:{player_ref}"
    if isinstance(player_ref, (list, tuple)) and len(player_ref) >= 3:
        return "pos:{:.2f},{:.2f},{:.2f}".format(
            float(player_ref[0]), float(player_ref[1]), float(player_ref[2]),
        )
    return str(player_ref)


def _endpoint_key(end_ref: Vec3Ref) -> str:
    if isinstance(end_ref, str):
        return end_ref
    if isinstance(end_ref, (list, tuple)) and len(end_ref) >= 3:
        return "pos:{:.2f},{:.2f},{:.2f}".format(
            float(end_ref[0]), float(end_ref[1]), float(end_ref[2]),
        )
    return str(end_ref)


def cache_key(poi_type: str, player_ref: Vec3Ref, end_ref: Vec3Ref) -> str:
    return f"{poi_type}|{_player_key(player_ref)}|{_endpoint_key(end_ref)}"


def clear_poi_type(poi_type: str) -> None:
    prefix = f"{poi_type}|"
    for key in list(_CACHE.keys()):
        if key.startswith(prefix):
            del _CACHE[key]


def store(
    poi_type: str,
    player_ref: Vec3Ref,
    end_ref: Vec3Ref,
    *,
    points: List[Point],
    via_points: List[Point],
    measure: Optional[RouteMeasure],
    segment_speeds: Optional[List[float]] = None,
    segment_classes: Optional[List[str]] = None,
    has_shortcut: bool = False,
) -> None:
    if len(points) < 2:
        return
    entry: CacheEntry = {
        "points": list(points),
        "via_points": list(via_points),
        "measure": measure,
        "has_shortcut": bool(has_shortcut),
    }
    if segment_speeds:
        entry["segment_speeds"] = list(segment_speeds)
    if segment_classes:
        entry["segment_classes"] = list(segment_classes)
    _CACHE[cache_key(poi_type, player_ref, end_ref)] = entry


def get(poi_type: str, player_ref: Vec3Ref, end_ref: Vec3Ref) -> Optional[CacheEntry]:
    return _CACHE.get(cache_key(poi_type, player_ref, end_ref))
