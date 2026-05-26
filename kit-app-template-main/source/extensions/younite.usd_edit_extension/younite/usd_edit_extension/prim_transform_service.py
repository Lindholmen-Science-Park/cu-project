"""
Prim transform service: select a prim and nudge its translate / rotate
via the session layer.  Edits can be saved to the shared edit sublayer.
"""

from .edit_layer_manager import EditLayerManager, _get_stage

# xformOp types we recognise for rotation
_ROTATE_OP_TYPES = None  # lazy-populated


def _rotate_op_types():
    global _ROTATE_OP_TYPES
    if _ROTATE_OP_TYPES is None:
        from pxr import UsdGeom
        _ROTATE_OP_TYPES = {
            UsdGeom.XformOp.TypeRotateXYZ,
            UsdGeom.XformOp.TypeRotateYXZ,
            UsdGeom.XformOp.TypeRotateZYX,
            UsdGeom.XformOp.TypeRotateXZY,
            UsdGeom.XformOp.TypeRotateYZX,
            UsdGeom.XformOp.TypeRotateZXY,
        }
    return _ROTATE_OP_TYPES


class PrimTransformService:
    def __init__(self, layer_mgr: EditLayerManager):
        self._layer_mgr = layer_mgr
        self._active_prim_path = None
        self._current_translate = None
        self._current_rotate = None
        self._has_translate_op = False
        self._has_rotate_op = False
        self._rotate_attr_name = "xformOp:rotateXYZ"
        self._edited_prim_paths: set = set()

    @property
    def active_prim_path(self):
        return self._active_prim_path

    @property
    def has_unsaved_edits(self) -> bool:
        return len(self._edited_prim_paths) > 0

    # ── Selection ────────────────────────────────────────────────────

    def select_prim(self, prim_path: str) -> dict:
        """Select a prim for transform editing. Returns current translate + rotate."""
        from pxr import UsdGeom, Gf

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return {"error": f"prim not found: {prim_path}"}

        xformable = UsdGeom.Xformable(prim)
        if not xformable:
            return {"error": f"prim is not transformable: {prim_path}"}

        translate = Gf.Vec3d(0, 0, 0)
        rotate = Gf.Vec3f(0, 0, 0)
        has_translate = False
        has_rotate = False
        rotate_attr = "xformOp:rotateXYZ"

        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                val = op.Get()
                if val is not None:
                    translate = Gf.Vec3d(val)
                has_translate = True
            elif op.GetOpType() in _rotate_op_types():
                val = op.Get()
                if val is not None:
                    rotate = Gf.Vec3f(val)
                has_rotate = True
                rotate_attr = op.GetOpName()

        self._active_prim_path = prim_path
        self._current_translate = translate
        self._current_rotate = rotate
        self._has_translate_op = has_translate
        self._has_rotate_op = has_rotate
        self._rotate_attr_name = rotate_attr

        print(f"[usd_edit:transform] Selected {prim_path}  "
              f"t=({translate[0]:.1f},{translate[1]:.1f},{translate[2]:.1f})  "
              f"r=({rotate[0]:.1f},{rotate[1]:.1f},{rotate[2]:.1f})")
        return self._make_result(prim_path, prim.GetName())

    # ── Nudge ────────────────────────────────────────────────────────

    def nudge_translate(self, dx: float, dy: float, dz: float) -> dict:
        """Nudge the selected prim's translate by delta."""
        from pxr import Usd, UsdGeom, Gf

        if not self._active_prim_path:
            return {"error": "no prim selected"}

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        prim = stage.GetPrimAtPath(self._active_prim_path)
        if not prim or not prim.IsValid():
            return {"error": "prim gone"}

        self._current_translate = self._current_translate + Gf.Vec3d(dx, dy, dz)

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            attr = prim.GetAttribute("xformOp:translate")
            if attr and attr.IsValid():
                attr.Set(self._current_translate)
            else:
                xformable = UsdGeom.Xformable(prim)
                op = xformable.AddTranslateOp()
                op.Set(self._current_translate)
                self._has_translate_op = True

        self._edited_prim_paths.add(self._active_prim_path)
        return self._make_result(self._active_prim_path, prim.GetName())

    def nudge_rotate(self, dx: float, dy: float, dz: float) -> dict:
        """Nudge the selected prim's rotation by delta (degrees)."""
        from pxr import Usd, UsdGeom, Gf

        if not self._active_prim_path:
            return {"error": "no prim selected"}

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        prim = stage.GetPrimAtPath(self._active_prim_path)
        if not prim or not prim.IsValid():
            return {"error": "prim gone"}

        self._current_rotate = Gf.Vec3f(
            float(self._current_rotate[0]) + dx,
            float(self._current_rotate[1]) + dy,
            float(self._current_rotate[2]) + dz,
        )

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            attr = prim.GetAttribute(self._rotate_attr_name)
            if attr and attr.IsValid():
                attr.Set(self._current_rotate)
            else:
                xformable = UsdGeom.Xformable(prim)
                op = xformable.AddRotateXYZOp()
                op.Set(self._current_rotate)
                self._has_rotate_op = True
                self._rotate_attr_name = op.GetOpName()

        self._edited_prim_paths.add(self._active_prim_path)
        return self._make_result(self._active_prim_path, prim.GetName())

    # ── Save / Reset ─────────────────────────────────────────────────

    def save_edits(self) -> int:
        """Copy session-layer xform overrides to the edit sublayer. Returns count."""
        from pxr import Usd

        if not self._edited_prim_paths:
            return 0

        stage = _get_stage()
        if not stage:
            return 0

        edit_layer = self._layer_mgr.ensure_edit_layer()
        if not edit_layer:
            return 0

        session = stage.GetSessionLayer()
        saved = 0
        xform_attrs = ("xformOp:translate", "xformOp:rotateXYZ", "xformOp:rotateYXZ",
                        "xformOp:rotateZYX", "xformOp:rotateXZY", "xformOp:rotateYZX",
                        "xformOp:rotateZXY")

        for prim_path in list(self._edited_prim_paths):
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                continue

            any_saved = False
            for attr_name in xform_attrs:
                attr = prim.GetAttribute(attr_name)
                if not attr or not attr.IsValid():
                    continue
                val = attr.Get()
                if val is None:
                    continue

                with Usd.EditContext(stage, Usd.EditTarget(edit_layer)):
                    attr.Set(val)

                with Usd.EditContext(stage, Usd.EditTarget(session)):
                    prim.RemoveProperty(attr_name)

                any_saved = True

            if any_saved:
                order_attr = prim.GetAttribute("xformOpOrder")
                if order_attr and order_attr.IsValid():
                    order_val = order_attr.Get()
                    if order_val is not None:
                        with Usd.EditContext(stage, Usd.EditTarget(edit_layer)):
                            order_attr.Set(order_val)
                        with Usd.EditContext(stage, Usd.EditTarget(session)):
                            prim.RemoveProperty("xformOpOrder")
                saved += 1

        self._edited_prim_paths.clear()
        return saved

    def reset_session(self) -> int:
        """Clear session-layer xform overrides. Returns count."""
        from pxr import Usd

        if not self._edited_prim_paths:
            return 0

        stage = _get_stage()
        if not stage:
            return 0

        session = stage.GetSessionLayer()
        xform_attrs = ("xformOp:translate", "xformOp:rotateXYZ", "xformOp:rotateYXZ",
                        "xformOp:rotateZYX", "xformOp:rotateXZY", "xformOp:rotateYZX",
                        "xformOp:rotateZXY", "xformOpOrder")
        reset = 0

        for prim_path in list(self._edited_prim_paths):
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                continue
            any_reset = False
            with Usd.EditContext(stage, Usd.EditTarget(session)):
                for attr_name in xform_attrs:
                    if prim.GetAttribute(attr_name).IsValid():
                        prim.RemoveProperty(attr_name)
                        any_reset = True
            if any_reset:
                reset += 1

        self._edited_prim_paths.clear()
        return reset

    # ── Exit ─────────────────────────────────────────────────────────

    def exit_transform_mode(self):
        was_active = self._active_prim_path is not None
        self._active_prim_path = None
        self._current_translate = None
        self._current_rotate = None
        if was_active:
            print("[usd_edit:transform] Exited transform mode")

    # ── Helpers ──────────────────────────────────────────────────────

    def _make_result(self, prim_path, prim_name):
        return {
            "primPath": prim_path,
            "primName": prim_name,
            "x": float(self._current_translate[0]),
            "y": float(self._current_translate[1]),
            "z": float(self._current_translate[2]),
            "rotX": float(self._current_rotate[0]),
            "rotY": float(self._current_rotate[1]),
            "rotZ": float(self._current_rotate[2]),
        }
