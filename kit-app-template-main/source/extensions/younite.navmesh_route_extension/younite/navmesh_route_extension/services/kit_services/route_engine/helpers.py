"""Small pure helpers used by the route engine."""

from __future__ import annotations

import re
from typing import Tuple


def point_in_world_aabb(
    p: Tuple[float, float, float],
    mn: Tuple[float, float, float],
    mx: Tuple[float, float, float],
) -> bool:
    return bool(
        mn[0] <= p[0] <= mx[0]
        and mn[1] <= p[1] <= mx[1]
        and mn[2] <= p[2] <= mx[2]
    )


def _safe_prim_name(value: str) -> str:
    """Turn an arbitrary id into a safe USD prim name fragment."""
    s = re.sub(r"[^A-Za-z0-9_]+", "_", str(value))
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "route"
