"""Read player root and first-person camera transforms from the USD stage."""

from __future__ import annotations

import math
from typing import Optional, Tuple


def get_player_xyz() -> Optional[Tuple[float, float, float]]:
    try:
        import omni.usd
        from pxr import Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return None
        prim = stage.GetPrimAtPath("/World/PlayerCharacter")
        if not (prim and prim.IsValid()):
            return None
        xf = UsdGeom.Xformable(prim)
        m = xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        t = m.ExtractTranslation()
        return (float(t[0]), float(t[1]), float(t[2]))
    except Exception:
        return None


def get_player_forward_xz() -> Optional[Tuple[float, float]]:
    """Normalised XZ look direction from ``first_person_camera`` (-Z forward)."""
    try:
        import omni.usd
        from pxr import Gf, Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return None
        cam = stage.GetPrimAtPath("/World/PlayerCharacter/first_person_camera")
        if not (cam and cam.IsValid()):
            return None
        xf = UsdGeom.Xformable(cam)
        m = xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        fwd = m.TransformDir(Gf.Vec3d(0.0, 0.0, -1.0))
        fx = float(fwd[0])
        fz = float(fwd[2])
        h = math.hypot(fx, fz)
        if h < 1e-6:
            return None
        return (fx / h, fz / h)
    except Exception:
        return None
