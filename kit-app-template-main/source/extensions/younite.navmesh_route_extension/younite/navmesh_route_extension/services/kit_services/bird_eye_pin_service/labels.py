"""Human-readable titles for waypoint and spawn magnet prims."""

from __future__ import annotations

from .constants import (
    ENTRANCE_PREFIX,
    SPAWN_POINT_LABELS,
    SPAWN_PREFIX,
    WAYPOINT_LABELS,
)


def waypoint_label(name: str) -> str:
    if name in WAYPOINT_LABELS:
        return WAYPOINT_LABELS[name]
    if name.startswith(ENTRANCE_PREFIX):
        idx = name[len(ENTRANCE_PREFIX) :]
        return f"Entrance {idx}"
    if name.startswith("nav_waypoint_"):
        suffix = name[len("nav_waypoint_") :]
        if len(suffix) == 1 and suffix.isalpha():
            return f"Section {suffix.upper()}"
        if len(suffix) == 2 and suffix.isalpha():
            return f"Near {suffix[0].upper()} / {suffix[1].upper()}"
    return name


def spawn_point_label(name: str) -> str:
    return (
        SPAWN_POINT_LABELS.get(name)
        or name.replace(SPAWN_PREFIX, "").replace("_", " ").strip()
        or name
    )
