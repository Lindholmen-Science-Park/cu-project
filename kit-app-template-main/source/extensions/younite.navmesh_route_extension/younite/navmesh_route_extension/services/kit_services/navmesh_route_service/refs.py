"""Normalise start/end references for route configuration."""

from __future__ import annotations

from typing import Any

from ..route_engine import Vec3Ref


def is_prim_path(ref: Any) -> bool:
    return isinstance(ref, str)


def normalize_vec3_ref(ref: Any) -> Vec3Ref:
    if isinstance(ref, str):
        return ref
    if isinstance(ref, (list, tuple)) and len(ref) >= 3:
        return (float(ref[0]), float(ref[1]), float(ref[2]))
    raise TypeError(f"Unsupported start/end reference type: {type(ref)}")
