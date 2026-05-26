"""Smooth Y-axis rotation service for interactive prims.

Typical use case: rotate an NPC so it faces the player when clicked. The
service maintains a small queue of in-flight rotations advanced once per
update frame by :meth:`tick`.
"""
from __future__ import annotations

from typing import Tuple


class RotationService:
    """Queue and tick smooth Y-axis rotations on USD prims."""

    def __init__(self) -> None:
        self._active: dict = {}

    def start_rotation_toward(
        self,
        prim_path: str,
        target_pos: Tuple[float, float, float],
        duration: float = 0.6,
    ) -> None:
        """Queue a smooth Y-axis rotation of ``prim_path`` toward ``target_pos``.

        Overwrites any in-flight rotation on the same prim.
        """
        try:
            import math
            import time
            import omni.usd
            from pxr import Usd, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                return
            orient_attr = prim.GetAttribute("xformOp:orient")
            if not orient_attr or not orient_attr.IsValid():
                return

            cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            l2w = cache.GetLocalToWorldTransform(prim)
            prim_pos = l2w.ExtractTranslation()

            cur = orient_attr.Get()
            start_angle = 2.0 * math.atan2(float(cur.GetImaginary()[1]), float(cur.GetReal()))

            dx = float(target_pos[0]) - float(prim_pos[0])
            dz = float(target_pos[2]) - float(prim_pos[2])
            end_angle = math.atan2(dx, dz)

            diff = end_angle - start_angle
            while diff > math.pi:
                diff -= 2.0 * math.pi
            while diff < -math.pi:
                diff += 2.0 * math.pi

            self._active[prim_path] = {
                "start_angle": start_angle,
                "diff": diff,
                "start_time": time.time(),
                "duration": duration,
            }
        except Exception:
            pass

    def tick(self) -> None:
        """Advance all queued rotations. Called once per update frame."""
        if not self._active:
            return
        try:
            import math
            import time
            import omni.usd
            from pxr import Gf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            now = time.time()
            done: list = []
            for prim_path, r in self._active.items():
                t = min((now - r["start_time"]) / r["duration"], 1.0)
                t_ease = t * t * (3.0 - 2.0 * t)
                angle = r["start_angle"] + r["diff"] * t_ease
                half = angle / 2.0
                quat = Gf.Quatf(math.cos(half), 0, math.sin(half), 0)

                prim = stage.GetPrimAtPath(prim_path)
                if prim and prim.IsValid():
                    orient_attr = prim.GetAttribute("xformOp:orient")
                    if orient_attr and orient_attr.IsValid():
                        orient_attr.Set(quat)
                if t >= 1.0:
                    done.append(prim_path)

            for p in done:
                self._active.pop(p, None)
        except Exception:
            pass

    def clear(self) -> None:
        """Drop all queued rotations."""
        self._active.clear()
