"""Data types for route distance / ETA results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Union

Vec3Ref = Union[str, Sequence[float]]


@dataclass
class RouteMeasure:
    """Distance and estimated time for a route (base = no crowd costs, actual = with crowd/costs)."""
    distance_meters_base: float = 0.0
    estimated_time_seconds_base: float = 0.0
    distance_meters_actual: Optional[float] = None
    estimated_time_seconds_actual: Optional[float] = None
    # Per-source deltas: how much each cost source adds vs. the base path
    distance_meters_crowd_delta: Optional[float] = None
    estimated_time_seconds_crowd_delta: Optional[float] = None
    distance_meters_sound_delta: Optional[float] = None
    estimated_time_seconds_sound_delta: Optional[float] = None
