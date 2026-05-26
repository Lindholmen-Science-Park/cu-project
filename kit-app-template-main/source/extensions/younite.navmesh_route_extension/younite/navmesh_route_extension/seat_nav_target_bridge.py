"""Active seat-nav target for Kit-side snap (same tuple as teleport).

Caches the world XYZ captured when ``seatNavigate`` runs so arrival matches
routing/teleport even if lookup or web ``endPos`` races. Player auto-move reads
``get_seat_nav_snap_world_position()`` **before** ``navmeshRouteStop`` clears state.
"""

from __future__ import annotations

from typing import Optional, Tuple

_active_seat_id: Optional[str] = None
_cached_snap_world: Optional[Tuple[float, float, float]] = None


def set_seat_nav_target_seat_id(
    seat_id: Optional[str],
    snap_world: Optional[Tuple[float, float, float]] = None,
) -> None:
    global _active_seat_id, _cached_snap_world
    if not seat_id:
        _active_seat_id = None
        _cached_snap_world = None
        return
    _active_seat_id = (str(seat_id).strip() if seat_id else None) or None
    if snap_world is not None and len(snap_world) >= 3:
        _cached_snap_world = (
            float(snap_world[0]),
            float(snap_world[1]),
            float(snap_world[2]),
        )
    else:
        _cached_snap_world = None


def get_seat_nav_target_seat_id() -> Optional[str]:
    return _active_seat_id


def get_seat_nav_snap_world_position() -> Optional[Tuple[float, float, float]]:
    """Cached navigate-time position, else ``get_seat_position(active id)``."""
    if _cached_snap_world is not None:
        return _cached_snap_world
    if not _active_seat_id:
        return None
    try:
        from .services.kit_services.seat_lookup import get_seat_position

        return get_seat_position(_active_seat_id)
    except Exception:
        return None
