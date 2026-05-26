"""Read xform transforms while ignoring volatile session-layer opinions.

The interactions extension's icon-spin loop overwrites
``xformOp:rotateXYZ`` for iconGroup markers in the **session** layer.
Anything that wants the *authored* direction (e.g.
``CameraService.enter_xform_view`` teleporting to a marker pose) must
skip session opinions or it inherits whatever spin sample was live
when the request arrived.

* ``read_authored_world_transform(stage, prim)`` →
  ``(translate_world, yaw_degrees)``
* ``compute_authored_local_transform(stage, prim)`` → local matrix

Both walk ``GetPropertyStack()`` for the strongest non-session opinion,
falling back to the composed value otherwise.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple


def compute_authored_local_transform(stage, prim):
    """Local matrix from strongest non-session opinions. Returns ``None`` on failure."""
    try:
        from pxr import UsdGeom, Usd, Sdf, Gf

        if not (prim and prim.IsValid()):
            return None
        xformable = UsdGeom.Xformable(prim)
        ops = xformable.GetOrderedXformOps()
        if not ops:
            return None

        session = stage.GetSessionLayer()
        time = Usd.TimeCode.Default()

        local = Gf.Matrix4d(1.0)
        for op in ops:
            attr = op.GetAttr()
            if not (attr and attr.IsValid()):
                return None

            authored_value = None
            for spec in attr.GetPropertyStack(time):
                if spec.layer == session:
                    continue
                candidate = spec.default
                if candidate is None or isinstance(candidate, Sdf.ValueBlock):
                    continue
                authored_value = candidate
                break

            composed_value = attr.Get(time)
            if authored_value is None:
                if composed_value is None:
                    return None
                authored_value = composed_value

            if authored_value == composed_value:
                # No session override — let USD do the matrix math.
                op_matrix = op.GetOpTransform(time)
            else:
                op_matrix = _build_op_matrix(op, authored_value)
            local = op_matrix * local
        return local
    except Exception:
        return None


def read_authored_world_transform(
    stage, prim
) -> Optional[Tuple[Tuple[float, float, float], float]]:
    """Return ``(translate_world, yaw_deg)`` from *prim*'s authored pose.

    Parent transforms still apply; only the prim's own session-layer
    overrides are ignored. Yaw = world angle of authored local -Z
    (USD forward), matching the dev marker arrow convention.
    """
    try:
        from pxr import UsdGeom, Usd, Gf

        if not (prim and prim.IsValid()):
            return None

        local = compute_authored_local_transform(stage, prim)
        parent_prim = prim.GetParent()
        if parent_prim and parent_prim.IsValid() and local is not None:
            parent_world = UsdGeom.Xformable(parent_prim).ComputeLocalToWorldTransform(
                Usd.TimeCode.Default()
            )
            world = local * parent_world
        elif local is not None:
            world = local
        else:
            world = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                Usd.TimeCode.Default()
            )

        translate = world.ExtractTranslation()
        fwd = world.TransformDir(Gf.Vec3d(0.0, 0.0, -1.0))
        fx, fz = float(fwd[0]), float(fwd[2])
        if (fx * fx + fz * fz) < 1e-12:
            yaw_deg = 0.0
        else:
            yaw_deg = math.degrees(math.atan2(-fx, -fz))
        return (
            (float(translate[0]), float(translate[1]), float(translate[2])),
            float(yaw_deg),
        )
    except Exception:
        return None


def _build_op_matrix(op, value):
    """Build a Gf.Matrix4d for *op* from manually-resolved *value*.

    Raises on unsupported op types so the caller falls back to the
    composed value (lesser evil vs. silently producing wrong matrix).
    """
    from pxr import UsdGeom, Gf

    op_type = op.GetOpType()
    if op_type == UsdGeom.XformOp.TypeTranslate:
        return Gf.Matrix4d().SetTranslate(Gf.Vec3d(value))
    if op_type == UsdGeom.XformOp.TypeScale:
        return Gf.Matrix4d().SetScale(Gf.Vec3d(value))
    if op_type == UsdGeom.XformOp.TypeRotateXYZ:
        rx = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), float(value[0])))
        ry = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), float(value[1])))
        rz = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), float(value[2])))
        return rx * ry * rz
    if op_type == UsdGeom.XformOp.TypeRotateYXZ:
        ry = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), float(value[0])))
        rx = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), float(value[1])))
        rz = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), float(value[2])))
        return ry * rx * rz
    if op_type == UsdGeom.XformOp.TypeRotateY:
        return Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), float(value)))
    if op_type == UsdGeom.XformOp.TypeRotateX:
        return Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), float(value)))
    if op_type == UsdGeom.XformOp.TypeRotateZ:
        return Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), float(value)))
    if op_type == UsdGeom.XformOp.TypeOrient:
        return Gf.Matrix4d().SetRotate(Gf.Rotation(value))
    if op_type == UsdGeom.XformOp.TypeTransform:
        return Gf.Matrix4d(value)
    raise ValueError(f"unsupported xform op type {op_type}")
