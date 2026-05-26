"""3D tetrahedron markers above interactive prims — glowing, rotating, bobbing.

Supports three modes:
  - "npc"  : single downward pyramid above the Collider top
  - "icon" : two pyramids (top + bottom) around prim center, plus prim self-rotation
  - "coin" : reserved for optional ``xformOp:rotate*:spin`` drive (POI coins no
            longer register here — spin stays at 0 from ``attach_coin_payload``).
"""

from __future__ import annotations

import math
import time

_MARKER_ROOT = "/World/_InteractionMarkers"
_MARKER_MATERIAL = f"{_MARKER_ROOT}/_MarkerMaterial"

_BASE_RADIUS = 10.0
_PYRAMID_HEIGHT = 15.0
_HOVER_OFFSET = 30.0
_BOB_AMPLITUDE = 4.0
_BOB_PERIOD = 2.5
_ROTATION_PERIOD = 4.0
_ICON_SELF_ROTATION_PERIOD = 12.0
_COIN_SPIN_PERIOD = 6.0  # seconds per full spin around the arrow axis

_GLOW_COLOR = (0.3, 1.0, 0.0)
_EMISSIVE_MULTIPLIER = 2.0


def _build_pyramid_down(stage, path, material):
    """Pyramid with apex pointing down (NPC style / icon top marker)."""
    from pxr import UsdGeom, UsdShade, Gf, Vt

    r, h = _BASE_RADIUS, _PYRAMID_HEIGHT
    sin60 = math.sin(math.radians(60))
    cos60 = math.cos(math.radians(60))

    v0 = Gf.Vec3f(0, 0, -r)
    v1 = Gf.Vec3f(r * sin60, 0, r * cos60)
    v2 = Gf.Vec3f(-r * sin60, 0, r * cos60)
    v3 = Gf.Vec3f(0, -h, 0)

    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([v0, v1, v2, v3]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([3, 3, 3, 3]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3]))
    mesh.GetDoubleSidedAttr().Set(True)
    mesh.GetDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*_GLOW_COLOR)]))
    mesh.GetExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(-r, -h, -r), Gf.Vec3f(r, 0, r)]))

    xformable = UsdGeom.Xformable(mesh.GetPrim())
    xformable.ClearXformOpOrder()
    xformable.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0))
    xformable.AddRotateYOp().Set(0.0)

    if material:
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh


def _build_pyramid_up(stage, path, material):
    """Pyramid with apex pointing up (icon bottom marker)."""
    from pxr import UsdGeom, UsdShade, Gf, Vt

    r, h = _BASE_RADIUS, _PYRAMID_HEIGHT
    sin60 = math.sin(math.radians(60))
    cos60 = math.cos(math.radians(60))

    v0 = Gf.Vec3f(0, 0, -r)
    v1 = Gf.Vec3f(r * sin60, 0, r * cos60)
    v2 = Gf.Vec3f(-r * sin60, 0, r * cos60)
    v3 = Gf.Vec3f(0, h, 0)

    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([v0, v1, v2, v3]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([3, 3, 3, 3]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([0, 1, 2, 0, 3, 1, 1, 3, 2, 2, 3, 0]))
    mesh.GetDoubleSidedAttr().Set(True)
    mesh.GetDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*_GLOW_COLOR)]))
    mesh.GetExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(-r, 0, -r), Gf.Vec3f(r, h, r)]))

    xformable = UsdGeom.Xformable(mesh.GetPrim())
    xformable.ClearXformOpOrder()
    xformable.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0))
    xformable.AddRotateYOp().Set(0.0)

    if material:
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh


class InteractionMarkerService:
    def __init__(self):
        self._markers: dict[str, dict] = {}
        self._start_time = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_markers(self, prim_paths: list[str], mode: str = "npc") -> None:
        """Create markers for the given prim paths.

        mode="npc"  — single downward pyramid above Collider top
        mode="icon" — top + bottom pyramids around prim center, prim self-rotation
        """
        try:
            import omni.usd
            from pxr import Usd, UsdShade

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                self._ensure_root(stage)
                material = self._ensure_material(stage)
                for prim_path in prim_paths:
                    if prim_path in self._markers:
                        continue
                    if mode == "npc":
                        self._create_npc_marker(stage, prim_path, material)
                    elif mode == "icon":
                        self._create_icon_markers(stage, prim_path, material)
        except Exception as e:
            print(f"[interactions] marker creation failed: {e}")

    def register_coin_spinners(self, paths_axes: list) -> None:
        """Register POI coin spinners as ``mode='coin'`` entries.

        ``paths_axes`` is a list of ``(coin_xform_prim_path, spin_axis)``
        tuples. The spin op (``xformOp:rotate{X|Y|Z}:spin``) on
        ``<coin_xform_prim_path>/CoinModel`` is authored elsewhere by
        :func:`session_authoring.attach_coin_payload`; this method just
        records what to drive in :meth:`update`. No geometry is created.

        Any prior ``mode='coin'`` registrations are cleared first so a
        config reload with ``spinEnabled: false`` (empty ``paths_axes``)
        stops driving spin ops instead of leaving stale entries.
        """
        drop = [k for k, v in self._markers.items() if v.get("mode") == "coin"]
        for k in drop:
            del self._markers[k]
        for entry in paths_axes:
            try:
                prim_path, axis = entry[0], entry[1]
            except Exception:
                continue
            if not prim_path or prim_path in self._markers:
                continue
            axis = (axis or "z").lower().strip()
            if axis == "x":
                attr_name = "xformOp:rotateX:spin"
            elif axis == "y":
                attr_name = "xformOp:rotateY:spin"
            else:
                attr_name = "xformOp:rotateZ:spin"
            self._markers[prim_path] = {
                "mode": "coin",
                "coin_model_path": f"{prim_path}/CoinModel",
                "spin_attr": attr_name,
            }

    # ------------------------------------------------------------------
    # Creation helpers
    # ------------------------------------------------------------------

    def _ensure_root(self, stage) -> None:
        from pxr import UsdGeom

        root = stage.GetPrimAtPath(_MARKER_ROOT)
        if not root or not root.IsValid():
            UsdGeom.Xform.Define(stage, _MARKER_ROOT)

    def _ensure_material(self, stage):
        from pxr import UsdShade, Sdf, Gf

        mat_prim = stage.GetPrimAtPath(_MARKER_MATERIAL)
        if mat_prim and mat_prim.IsValid():
            return UsdShade.Material(mat_prim)

        material = UsdShade.Material.Define(stage, _MARKER_MATERIAL)
        shader = UsdShade.Shader.Define(stage, f"{_MARKER_MATERIAL}/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")

        emissive = Gf.Vec3f(
            _GLOW_COLOR[0] * _EMISSIVE_MULTIPLIER,
            _GLOW_COLOR[1] * _EMISSIVE_MULTIPLIER,
            _GLOW_COLOR[2] * _EMISSIVE_MULTIPLIER,
        )
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0, 0, 0))
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(emissive)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        return material

    # ------------------------------------------------------------------

    def _create_npc_marker(self, stage, prim_path: str, material) -> None:
        """Single downward-pointing pyramid above the NPC Collider top."""
        top = self._get_collider_top(stage, prim_path)
        if top is None:
            print(f"[interactions] no Collider top for {prim_path}, skipping marker")
            return

        safe = prim_path.replace("/", "_").strip("_")
        marker_path = f"{_MARKER_ROOT}/{safe}"
        if self._prim_exists(stage, marker_path):
            return

        _build_pyramid_down(stage, marker_path, material)
        base_y = top[1] + _HOVER_OFFSET

        self._markers[prim_path] = {
            "mode": "npc",
            "top_path": marker_path,
            "base_x": top[0],
            "base_y": base_y,
            "base_z": top[2],
        }

    def _create_icon_markers(self, stage, prim_path: str, material) -> None:
        """Two pyramids (top down-pointing, bottom up-pointing) + icon self-rotation."""
        from pxr import UsdGeom, Gf

        center = self._get_prim_world_pos(stage, prim_path)
        if center is None:
            print(f"[interactions] cannot resolve position for {prim_path}, skipping markers")
            return

        safe = prim_path.replace("/", "_").strip("_")
        top_path = f"{_MARKER_ROOT}/{safe}_top"
        bot_path = f"{_MARKER_ROOT}/{safe}_bot"

        if not self._prim_exists(stage, top_path):
            _build_pyramid_down(stage, top_path, material)
        if not self._prim_exists(stage, bot_path):
            _build_pyramid_up(stage, bot_path, material)

        icon_height_offset = 50.0
        bot_offset = 20.0

        self._markers[prim_path] = {
            "mode": "icon",
            "top_path": top_path,
            "bot_path": bot_path,
            "icon_prim_path": prim_path,
            "base_x": center[0],
            "base_y_top": center[1] + icon_height_offset,
            "base_y_bot": center[1] - bot_offset,
            "base_z": center[2],
        }

    # ------------------------------------------------------------------
    # Position helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_collider_top(stage, prim_path: str):
        from pxr import UsdGeom, Usd, Gf

        collider = stage.GetPrimAtPath(f"{prim_path}/Collider")
        if not collider or not collider.IsValid():
            return None
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        l2w = cache.GetLocalToWorldTransform(collider)
        top = l2w.Transform(Gf.Vec3d(0, 1, 0))
        return (float(top[0]), float(top[1]), float(top[2]))

    @staticmethod
    def _get_prim_world_pos(stage, prim_path: str):
        from pxr import UsdGeom, Usd, Gf

        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return None
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        l2w = cache.GetLocalToWorldTransform(prim)
        pos = l2w.Transform(Gf.Vec3d(0, 0, 0))
        return (float(pos[0]), float(pos[1]), float(pos[2]))

    @staticmethod
    def _prim_exists(stage, path: str) -> bool:
        p = stage.GetPrimAtPath(path)
        return p is not None and p.IsValid()

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------

    def hide(self) -> None:
        self._set_visibility(invisible=True)

    def show(self) -> None:
        self._set_visibility(invisible=False)

    def _set_visibility(self, invisible: bool) -> None:
        try:
            import omni.usd
            from pxr import UsdGeom, Usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                for info in self._markers.values():
                    for key in ("top_path", "bot_path"):
                        path = info.get(key)
                        if not path:
                            continue
                        prim = stage.GetPrimAtPath(path)
                        if not prim or not prim.IsValid():
                            continue
                        img = UsdGeom.Imageable(prim)
                        if invisible:
                            img.MakeInvisible()
                        else:
                            img.MakeVisible()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Per-frame animation
    # ------------------------------------------------------------------

    def update(self) -> None:
        if not self._markers:
            return
        try:
            import omni.usd
            from pxr import Gf, UsdGeom, Usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            t = time.time() - self._start_time
            bob_y = _BOB_AMPLITUDE * math.sin(2.0 * math.pi * t / _BOB_PERIOD)
            rot_deg = (t / _ROTATION_PERIOD) * 360.0
            icon_rot_deg = (t / _ICON_SELF_ROTATION_PERIOD) * 360.0
            coin_spin_deg = (t / _COIN_SPIN_PERIOD) * 360.0

            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                for info in self._markers.values():
                    mode = info.get("mode", "npc")
                    if mode == "npc":
                        self._update_npc(stage, info, bob_y, rot_deg)
                    elif mode == "icon":
                        self._update_icon(stage, info, bob_y, rot_deg, icon_rot_deg)
                    elif mode == "coin":
                        self._update_coin(stage, info, coin_spin_deg)
        except Exception:
            pass

    @staticmethod
    def _update_npc(stage, info, bob_y, rot_deg):
        from pxr import Gf, UsdGeom

        prim = stage.GetPrimAtPath(info["top_path"])
        if not prim or not prim.IsValid():
            return
        ops = UsdGeom.Xformable(prim).GetOrderedXformOps()
        if len(ops) >= 2:
            ops[0].Set(Gf.Vec3d(info["base_x"], info["base_y"] + bob_y, info["base_z"]))
            ops[1].Set(rot_deg % 360.0)

    @staticmethod
    def _update_coin(stage, info, spin_deg):
        """Animate the ``xformOp:rotate{X|Y|Z}:spin`` op on ``CoinModel``.

        The spin op was authored as the **outermost** xformOp by
        :func:`session_authoring.attach_coin_payload`, so writing here
        rotates the corrected coin geometry around its arrow axis in
        CoinModel local space — the arrow tip stays put while the disk
        spins like a wheel on the arrow shaft.
        """
        coin_model_path = info.get("coin_model_path", "")
        spin_attr_name = info.get("spin_attr", "")
        if not coin_model_path or not spin_attr_name:
            return
        prim = stage.GetPrimAtPath(coin_model_path)
        if not prim or not prim.IsValid():
            return
        attr = prim.GetAttribute(spin_attr_name)
        if not attr or not attr.IsValid():
            return
        attr.Set(float(spin_deg % 360.0))

    @staticmethod
    def _update_icon(stage, info, bob_y, rot_deg, icon_rot_deg):
        from pxr import Gf, UsdGeom

        top = stage.GetPrimAtPath(info["top_path"])
        if top and top.IsValid():
            ops = UsdGeom.Xformable(top).GetOrderedXformOps()
            if len(ops) >= 2:
                ops[0].Set(Gf.Vec3d(info["base_x"], info["base_y_top"] + bob_y, info["base_z"]))
                ops[1].Set(rot_deg % 360.0)

        bot = stage.GetPrimAtPath(info.get("bot_path", ""))
        if bot and bot.IsValid():
            ops = UsdGeom.Xformable(bot).GetOrderedXformOps()
            if len(ops) >= 2:
                ops[0].Set(Gf.Vec3d(info["base_x"], info["base_y_bot"] - bob_y, info["base_z"]))
                ops[1].Set((-rot_deg) % 360.0)

        icon_prim = stage.GetPrimAtPath(info.get("icon_prim_path", ""))
        if icon_prim and icon_prim.IsValid():
            # Skip the per-frame spin if the icon is currently invisible.
            # This lets external tools (e.g. younite.usd_edit_extension's
            # marker editor) hide the icon and edit its xformOp:rotateXYZ
            # without us immediately overwriting their value next frame.
            try:
                if UsdGeom.Imageable(icon_prim).ComputeVisibility() == UsdGeom.Tokens.invisible:
                    return
            except Exception:
                pass
            rot_attr = icon_prim.GetAttribute("xformOp:rotateXYZ")
            if rot_attr and rot_attr.IsValid():
                from pxr import Gf as _Gf
                rot_attr.Set(_Gf.Vec3f(0, icon_rot_deg % 360.0, 0))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        try:
            import omni.usd
            from pxr import Usd

            stage = omni.usd.get_context().get_stage()
            if stage:
                session = stage.GetSessionLayer()
                with Usd.EditContext(stage, session):
                    root = stage.GetPrimAtPath(_MARKER_ROOT)
                    if root and root.IsValid():
                        stage.RemovePrim(_MARKER_ROOT)
        except Exception:
            pass
        self._markers.clear()
