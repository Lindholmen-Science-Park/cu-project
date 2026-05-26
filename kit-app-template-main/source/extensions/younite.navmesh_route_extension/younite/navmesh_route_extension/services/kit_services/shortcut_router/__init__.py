"""
Shortcut router — augmented-graph hop planning over NavMesh distances.

Package layout (under ``kit_services/shortcut_router/``):

* ``constants.py`` — walk-equivalent speed, elevator vertical thresholds, slack.
* ``types.py`` — ``ShortcutNode`` / ``ShortcutGroup`` / ``ShortcutPlan`` / ``WalkLenFn``.
* ``vertical_filters.py`` — hop exit Y validity (basement dip, prefer landing).
* ``config_io.py`` — resolve and load ``shortcuts.json``.
* ``usd_scan.py`` — leaf Xform positions under ``/World/NavShortcuts``.
* ``groups.py`` — JSON + positions → ``ShortcutGroup`` dict.
* ``shortcut_router.py`` — ``ShortcutRouter`` class and ``find_best_plan``.
* ``singleton.py`` — ``get_shortcut_router`` / ``set_shortcut_router``.

Import surface unchanged: ``from ...kit_services.shortcut_router import ShortcutRouter``.
"""
from __future__ import annotations

from .shortcut_router import ShortcutRouter
from .singleton import get_shortcut_router, set_shortcut_router
from .types import (
    ShortcutGroup,
    ShortcutHop,
    ShortcutNode,
    ShortcutPlan,
    Vec3,
    WalkLenFn,
)

__all__ = [
    "ShortcutRouter",
    "ShortcutNode",
    "ShortcutGroup",
    "ShortcutHop",
    "ShortcutPlan",
    "Vec3",
    "WalkLenFn",
    "set_shortcut_router",
    "get_shortcut_router",
]
