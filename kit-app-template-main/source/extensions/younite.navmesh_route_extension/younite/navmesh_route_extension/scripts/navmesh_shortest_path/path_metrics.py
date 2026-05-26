"""Polyline length, walk-time estimate, and optional Laplacian smoothing on XZ."""

from __future__ import annotations

import math
from typing import Any, List, Sequence, Tuple

from .constants import (
    PATH_SMOOTH_ALPHA,
    PATH_SMOOTH_ITERATIONS,
    PATH_SMOOTH_MIN_POINTS,
)


def smooth_path_xz(
    points: List[Tuple[float, float, float]],
    *,
    alpha: float = PATH_SMOOTH_ALPHA,
    iterations: int = PATH_SMOOTH_ITERATIONS,
    min_points: int = PATH_SMOOTH_MIN_POINTS,
) -> List[Tuple[float, float, float]]:
    """Laplacian smoothing on XZ only; Y preserved from the NavMesh polyline."""
    n = len(points)
    if n < min_points or iterations <= 0 or alpha <= 0.0:
        return points

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]

    keep = 1.0 - alpha
    half_alpha = alpha * 0.5

    for _ in range(iterations):
        new_xs = list(xs)
        new_zs = list(zs)
        for i in range(1, n - 1):
            new_xs[i] = keep * xs[i] + half_alpha * (xs[i - 1] + xs[i + 1])
            new_zs[i] = keep * zs[i] + half_alpha * (zs[i - 1] + zs[i + 1])
        xs = new_xs
        zs = new_zs

    return [(xs[i], ys[i], zs[i]) for i in range(n)]


def path_length_cm(points: Union[List[Any], Sequence[Any]]) -> float:
    """
    Total path length in stage units (cm). Accepts ``Gf.Vec3f`` or indexable triples.
    Returns 0.0 if fewer than 2 points.
    """
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(points)):
        p0, p1 = points[i - 1], points[i]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        dz = p1[2] - p0[2]
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


def estimate_walk_time_seconds(length_cm: float, speed_m_per_s: float = 1.4) -> float:
    """ETA from path length (cm) and speed (m/s)."""
    if speed_m_per_s <= 0:
        return 0.0
    length_m = length_cm / 100.0
    return length_m / speed_m_per_s
