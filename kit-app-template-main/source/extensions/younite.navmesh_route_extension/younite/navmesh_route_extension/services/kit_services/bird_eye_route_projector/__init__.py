"""Bird's-eye route overlay projector.

Receives a computed 3D route polyline, simplifies it (Douglas–Peucker), and
projects waypoints to screen coordinates for the web SVG overlay. Does not
compute routes — see :class:`BirdEyeRouteProjector` in ``projector``.
"""

from __future__ import annotations

from .constants import RDP_EPSILON_CM, UPDATE_INTERVAL_MS
from .projector import BirdEyeRouteProjector
from .types import Vec3

__all__ = [
    "BirdEyeRouteProjector",
    "RDP_EPSILON_CM",
    "UPDATE_INTERVAL_MS",
    "Vec3",
]
