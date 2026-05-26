"""Shared typing aliases for NavMesh path helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, Union

if TYPE_CHECKING:
    from pxr import Gf

# Prim path string, raw tuple/list, or USD vec types
Vec3Ref = Union[str, Sequence[float], "Gf.Vec3d", "Gf.Vec3f"]
