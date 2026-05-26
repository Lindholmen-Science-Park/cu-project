"""Hooks for sibling extensions that need the dual-mode cache + rebake scheduler.

Populated by ``NavMeshRouteExtension`` after the bake orchestrator exists; cleared on
shutdown. Used by ``younite.navmesh_dev_overlays_extension`` (dev streaming only).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

_mode_cache: Optional[Any] = None
_schedule_rebake_if_idle: Optional[Callable[[], None]] = None


def set_navmesh_route_dev_hooks(mode_cache: Any, schedule_rebake_if_idle: Callable[[], None]) -> None:
    global _mode_cache, _schedule_rebake_if_idle
    _mode_cache = mode_cache
    _schedule_rebake_if_idle = schedule_rebake_if_idle


def clear_navmesh_route_dev_hooks() -> None:
    global _mode_cache, _schedule_rebake_if_idle
    _mode_cache = None
    _schedule_rebake_if_idle = None


def get_navmesh_mode_cache_for_dev() -> Optional[Any]:
    return _mode_cache


def schedule_navmesh_rebake_if_idle() -> None:
    fn = _schedule_rebake_if_idle
    if fn is None:
        return
    try:
        fn()
    except Exception as exc:
        print(f"[navmesh_route_bridge] schedule rebake failed: {exc}")
