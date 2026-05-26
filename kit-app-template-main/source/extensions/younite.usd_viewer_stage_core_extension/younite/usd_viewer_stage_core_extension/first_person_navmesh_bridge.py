"""Registered by navmesh_route_extension so stage_core can await FP navmesh prep without a hard dependency cycle."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

_prepare: Optional[Callable[[], Awaitable[bool]]] = None


def set_first_person_navmesh_prepare(coro_fn: Optional[Callable[[], Awaitable[bool]]]) -> None:
    global _prepare
    _prepare = coro_fn


async def await_first_person_navmesh_prepare() -> bool:
    if _prepare is None:
        return True
    try:
        return bool(await _prepare())
    except Exception:
        return False
