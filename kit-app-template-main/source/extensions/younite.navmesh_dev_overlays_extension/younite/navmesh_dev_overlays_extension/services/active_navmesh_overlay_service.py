"""
Dev-only USD overlay of the **currently active** cached NavMesh (walking or wheelchair).

Unlike Composer's navigation UI, streaming Kit has no ``omni.anim.navigation.ui``; we
triangulate ``INavMesh.get_draw_triangles`` into a translucent mesh under
``/World/NavMeshDebugOverlay`` so match-mode geometry is visible in the Kit viewport.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

from .navmesh_draw_helpers import xyz_from_draw_point

_PAYLOAD_ORCH_SOURCE = "younite.navmesh_dev_overlays"

_OVERLAY_ROOT = "/World/NavMeshDebugOverlay"
_MESH_PATH = "/World/NavMeshDebugOverlay/Mesh"
_MATERIAL_PATH = "/World/NavMeshDebugOverlay/DebugMaterial"
_Y_LIFT_CM = 4.0
_OVERLAY_ALG_VERSION = 1

_DIFFUSE = (0.15, 0.72, 0.92)
_EMISSIVE_MUL = 0.35
_WARN_TRI_COUNT = 350_000


class ActiveNavMeshOverlayService:
    """Toggles visibility + rebuilds geometry for the active dual-cache mesh."""

    def __init__(self, mode_cache) -> None:
        self._mode_cache = mode_cache
        self._feature_enabled: bool = False
        self._overlay_visible: bool = False
        self._last_recompute_key: Optional[Tuple[int, str, int]] = None

    def is_feature_enabled(self) -> bool:
        return self._feature_enabled

    def _clear_feature_state(self) -> None:
        self._last_recompute_key = None
        self._strip_usd()
        try:
            from younite.payload_orchestrator_core_extension import hide, Priority

            hide(_OVERLAY_ROOT, Priority.LOW, source=_PAYLOAD_ORCH_SOURCE)
        except Exception:
            pass

    def set_feature_enabled(self, enabled: bool) -> None:
        en = bool(enabled)
        self._feature_enabled = en
        self._overlay_visible = en
        if not en:
            self._clear_feature_state()
        else:
            try:
                from younite.payload_orchestrator_core_extension import show_hide, Priority

                show_hide(_OVERLAY_ROOT, True, Priority.MEDIUM, source=_PAYLOAD_ORCH_SOURCE)
            except Exception as exc:
                print(f"[NAVMESH_DEBUG] overlay visibility request failed: {exc}")
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2("navmeshDebugStatus", {"visible": en})
        except Exception:
            pass
        try:
            from younite.usd_viewer_stage_core_extension.services.core_services.world_state_sync_service import (
                get_world_state_sync_service,
            )

            wss = get_world_state_sync_service()
            if wss:
                wss.set("navmeshDebugOverlayVisible", en)
        except Exception:
            pass

    def _strip_usd(self) -> None:
        try:
            import omni.usd
            from pxr import Usd
        except Exception:
            return
        ctx = omni.usd.get_context()
        stage = ctx.get_stage() if ctx else None
        if not stage:
            return
        root = stage.GetPrimAtPath(_OVERLAY_ROOT)
        if not root or not root.IsValid():
            return
        try:
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                stage.RemovePrim(_OVERLAY_ROOT)
        except Exception:
            pass

    def _rebuild_mesh(self, nav) -> None:
        try:
            import omni.usd
            from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt
        except Exception as exc:
            print(f"[NAVMESH_DEBUG] USD import failed: {exc}")
            return

        ctx = omni.usd.get_context()
        stage = ctx.get_stage() if ctx else None
        if not stage:
            return

        pts: List[Gf.Vec3f] = []
        f_counts: List[int] = []
        f_indices: List[int] = []
        lift = float(_Y_LIFT_CM)
        tri_total = 0

        try:
            n_areas = int(nav.get_area_count())
        except Exception:
            n_areas = 0

        for ai in range(n_areas):
            try:
                raw = nav.get_draw_triangles(ai)
            except Exception:
                continue
            ptl = list(raw) if raw is not None else []
            n = len(ptl)
            if n < 3 or n % 3 != 0:
                continue
            for i in range(0, n, 3):
                base = len(pts)
                for k in range(3):
                    vx, vy, vz = xyz_from_draw_point(ptl[i + k])
                    pts.append(Gf.Vec3f(float(vx), float(vy) + lift, float(vz)))
                f_counts.append(3)
                f_indices.extend([base, base + 1, base + 2])
                tri_total += 1

        if tri_total > _WARN_TRI_COUNT:
            print(
                f"[NAVMESH_DEBUG] WARNING: {tri_total} NavMesh triangles in overlay — "
                "expect slower build / heavier Hydra."
            )

        if len(pts) < 3:
            print("[NAVMESH_DEBUG] active NavMesh has no drawable triangles")
            return

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, session):
            root = stage.GetPrimAtPath(_OVERLAY_ROOT)
            if root and root.IsValid():
                try:
                    stage.RemovePrim(_OVERLAY_ROOT)
                except Exception:
                    pass

            UsdGeom.Xform.Define(stage, _OVERLAY_ROOT)
            mat = UsdShade.Material.Define(stage, _MATERIAL_PATH)
            shader = UsdShade.Shader.Define(stage, _MATERIAL_PATH + "/Shader")
            shader.CreateIdAttr("UsdPreviewSurface")
            dc = Gf.Vec3f(float(_DIFFUSE[0]), float(_DIFFUSE[1]), float(_DIFFUSE[2]))
            em = Gf.Vec3f(
                float(_DIFFUSE[0]) * _EMISSIVE_MUL,
                float(_DIFFUSE[1]) * _EMISSIVE_MUL,
                float(_DIFFUSE[2]) * _EMISSIVE_MUL,
            )
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(dc)
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(em)
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
            shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.32)
            try:
                shader.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(0.0)
            except Exception:
                pass
            mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

            mesh = UsdGeom.Mesh.Define(stage, _MESH_PATH)
            mesh_prim = mesh.GetPrim()
            mesh.CreatePointsAttr(Vt.Vec3fArray(pts))
            mesh.CreateFaceVertexCountsAttr(Vt.IntArray(f_counts))
            mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(f_indices))
            try:
                mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
            except Exception:
                pass
            try:
                mesh.CreateDoubleSidedAttr(True)
            except Exception:
                pass
            try:
                UsdShade.MaterialBindingAPI.Apply(mesh_prim)
                UsdShade.MaterialBindingAPI(mesh_prim).Bind(mat)
            except Exception:
                pass

    def recompute(self) -> bool:
        if not self._feature_enabled:
            return True
        t0 = time.perf_counter()
        nav = self._mode_cache.get_active_navmesh() if self._mode_cache else None
        if nav is None:
            print("[NAVMESH_DEBUG] recompute skipped — no active NavMesh handle")
            return False
        try:
            sig = int(nav.get_mesh_signature())
        except Exception:
            sig = 0
        try:
            mode = str(self._mode_cache.get_active_mode() or "walking")
        except Exception:
            mode = "walking"
        key = (sig, mode, _OVERLAY_ALG_VERSION)
        if self._last_recompute_key == key:
            return True

        self._rebuild_mesh(nav)
        self._last_recompute_key = key

        try:
            from younite.payload_orchestrator_core_extension import show_hide, hide, Priority

            if self._overlay_visible:
                show_hide(_OVERLAY_ROOT, True, Priority.MEDIUM, source=_PAYLOAD_ORCH_SOURCE)
            else:
                hide(_OVERLAY_ROOT, Priority.LOW, source=_PAYLOAD_ORCH_SOURCE)
        except Exception:
            pass

        print(
            f"[NAVMESH_DEBUG] overlay rebuilt in {(time.perf_counter()-t0)*1000:.1f}ms "
            f"(mode={mode}, sig={sig})"
        )
        return True
