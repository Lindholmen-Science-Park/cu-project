"""Shorter-arc traversal on the sorted corridor ring."""
from __future__ import annotations

from typing import List, Tuple

from .geom import dist_xz


def ring_path(ring_len: int, from_idx: int, to_idx: int) -> List[int]:
    """
    Return the shorter traversal around the ring (excluding ``from_idx``
    itself but including ``to_idx``).  If both directions are equal length,
    prefers the forward (CW) direction.
    """
    if from_idx == to_idx:
        return [from_idx]

    fwd: List[int] = []
    i = (from_idx + 1) % ring_len
    while True:
        fwd.append(i)
        if i == to_idx:
            break
        i = (i + 1) % ring_len

    bwd: List[int] = []
    i = (from_idx - 1) % ring_len
    while True:
        bwd.append(i)
        if i == to_idx:
            break
        i = (i - 1) % ring_len

    return fwd if len(fwd) <= len(bwd) else bwd


def ring_travel_distance(
    ring: List[Tuple[str, Tuple[float, float, float]]],
    from_idx: int,
    to_idx: int,
) -> float:
    """Sum of XZ distances along the shorter ring traversal."""
    path = ring_path(len(ring), from_idx, to_idx)
    if not path:
        return 0.0
    total = dist_xz(ring[from_idx][1], ring[path[0]][1])
    for i in range(1, len(path)):
        total += dist_xz(ring[path[i - 1]][1], ring[path[i]][1])
    return total
