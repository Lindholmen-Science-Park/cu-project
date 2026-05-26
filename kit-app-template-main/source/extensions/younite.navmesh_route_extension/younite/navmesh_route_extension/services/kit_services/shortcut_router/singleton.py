"""Process-wide optional ``ShortcutRouter`` for route composer."""
from __future__ import annotations

from typing import Optional

from .shortcut_router import ShortcutRouter

_router: Optional[ShortcutRouter] = None


def set_shortcut_router(router: Optional[ShortcutRouter]) -> None:
    global _router
    _router = router


def get_shortcut_router() -> Optional[ShortcutRouter]:
    return _router
