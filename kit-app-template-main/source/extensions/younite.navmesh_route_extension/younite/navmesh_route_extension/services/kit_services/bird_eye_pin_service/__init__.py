"""Bird-eye click-anywhere pin — magnets, OSM snap, sheet dispatch, projector hooks.

Public entry point: :class:`BirdEyePinService` in ``service``.
"""

from __future__ import annotations

from .constants import MAX_MAGNET_SNAP_XZ_CM
from .magnets import iter_named_spawn_points
from .osm import BirdEyePinOsmSnap
from .service import BirdEyePinService

# Doc compatibility (topics reference ``bird_eye_pin_service._iter_*``).
_iter_named_spawn_points = iter_named_spawn_points

__all__ = [
    "BirdEyePinOsmSnap",
    "BirdEyePinService",
    "MAX_MAGNET_SNAP_XZ_CM",
    "_iter_named_spawn_points",
    "iter_named_spawn_points",
]
