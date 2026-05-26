"""Helpers for ``INavMesh.get_draw_triangles`` point payloads (carb / tuple-like)."""
from __future__ import annotations

from typing import Any, Tuple


def xyz_from_draw_point(p: Any) -> Tuple[float, float, float]:
    if hasattr(p, "x"):
        return (float(p.x), float(p.y), float(p.z))
    return (float(p[0]), float(p[1]), float(p[2]))
