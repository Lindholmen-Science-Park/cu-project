"""
Walking vs wheelchair NavMesh diff — stair / tall-step surfaces only (Kit viewport).

Uses ``INavMesh.get_draw_triangles`` on the walking mesh and
``query_closest_point`` on the wheelchair mesh; classifies triangles whose
height **above a low-quantile "flat" ΔY** sample exceeds roughly one walking
step, clusters them, and builds a translucent USD overlay under
``/World/AccessibilityOverlay``.

The pipeline is **off** until dev **NavMesh diff** (``accessibilityDiffShow``)
enables it; no diff work runs during ordinary navmesh rebakes while disabled.
No cluster or click data is sent to the browser — visuals are Kit-only.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

import carb

from .navmesh_draw_helpers import xyz_from_draw_point as _xyz

# Payload orchestrator visibility source for this extension
_PAYLOAD_ORCH_SOURCE = "younite.navmesh_dev_overlays"

# USD / stage paths (relative to stage root)
_OVERLAY_ROOT = "/World/AccessibilityOverlay"
_STAIR_BLOCKS = "/World/AccessibilityOverlay/StairBlocks"
_MATERIAL_PATH = "/World/AccessibilityOverlay/StairBlockMaterial"

_VERTEX_RES_CM = 5.0
_Y_LIFT_CM = 5.0
# Additional |Y − wheelchair| beyond the sampled flat baseline (see below).
_MIN_STEP_CM = 18.0
_STEP_HEIGHT_FACTOR = 1.0
# Strided sample for bake-offset estimate (not the 50th percentile — see _FLAT_OFFSET_QUANTILE).
_MEDIAN_SAMPLE_STRIDE = 4
_MEDIAN_SAMPLE_CAP = 3072
_MEDIAN_ABS_CLAMP_CM = 40.0
# Lower than 0.5: subtract a smaller "flat mesh" bias so stair treads (often ~one step
# above the wheelchair surface) still exceed threshold after baseline removal.
_FLAT_OFFSET_QUANTILE = 0.12
# Include single-triangle components — lower stair treads are often 1–2 tris.
_MIN_CLUSTER_TRIS = 1
# Risers / ramps: always vertex-probe when vertical span is at least this.
_MIN_Y_SPAN_FOR_VERTEX_PROBE_CM = 8.0
# Centroid-only miss: still vertex-probe if excess > -(this × step_thresh) — catches flat treads, skips deep floor.
_VERTEX_NEAR_MISS_FRAC = 0.5
# Fallback when baseline subtraction eats most of a real step: high raw |ΔY|, moderate excess.
_STAIR_RAW_HIGH_CM = 22.0
_STAIR_RAW_WITH_EXCESS_CM = 7.0

# Bump when triangle/cluster rules change so mesh-signature cache still recomputes.
_DIFF_ALG_VERSION = 7

# Emissive red in Kit viewport
_DIFFUSE = (0.95, 0.12, 0.12)
_EMISSIVE_MUL = 4.0


def _vkey(x: float, y: float, z: float) -> Tuple[int, int, int]:
    r = _VERTEX_RES_CM
    return (
        int(round(float(x) / r)),
        int(round(float(y) / r)),
        int(round(float(z) / r)),
    )


def _edge_key(
    a: Tuple[int, int, int], b: Tuple[int, int, int]
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    return (a, b) if a < b else (b, a)


def _wheelchair_closest_y(wheelchair, x: float, y: float, z: float) -> Optional[float]:
    """Return Y of closest point on wheelchair mesh, or None if off-mesh."""
    try:
        snap = wheelchair.query_closest_point(target=carb.Float3(float(x), float(y), float(z)))
    except Exception:
        return None
    if snap is None or snap[0] is None:
        return None
    cp, _island = snap
    try:
        return float(cp.y)
    except Exception:
        try:
            return float(cp[1])
        except Exception:
            return None


def _sampled_flat_y_offset(walking, wheelchair) -> float:
    """Low-quantile |ΔY| on a strided centroid sample — typical flat-ground bake skew, not stair-dominated."""
    samples: List[float] = []
    tri_i = 0
    try:
        n_areas = int(walking.get_area_count())
    except Exception:
        n_areas = 0
    for ai in range(n_areas):
        try:
            raw = walking.get_draw_triangles(ai)
        except Exception:
            continue
        pts = list(raw) if raw is not None else []
        n = len(pts)
        if n < 3 or n % 3 != 0:
            continue
        for i in range(0, n, 3):
            if tri_i % _MEDIAN_SAMPLE_STRIDE != 0:
                tri_i += 1
                continue
            a = _xyz(pts[i])
            b = _xyz(pts[i + 1])
            c = _xyz(pts[i + 2])
            cx = (a[0] + b[0] + c[0]) / 3.0
            cy = (a[1] + b[1] + c[1]) / 3.0
            cz = (a[2] + b[2] + c[2]) / 3.0
            cpy_c = _wheelchair_closest_y(wheelchair, cx, cy, cz)
            tri_i += 1
            if cpy_c is None:
                continue
            samples.append(abs(float(cy) - cpy_c))
            if len(samples) >= _MEDIAN_SAMPLE_CAP:
                break
        if len(samples) >= _MEDIAN_SAMPLE_CAP:
            break
    if not samples:
        return 0.0
    samples.sort()
    q = float(_FLAT_OFFSET_QUANTILE)
    q = max(0.0, min(1.0, q))
    idx = int(round((len(samples) - 1) * q))
    idx = max(0, min(len(samples) - 1, idx))
    return min(float(samples[idx]), _MEDIAN_ABS_CLAMP_CM)


def _triangle_is_walking_only_vs_wheelchair(
    wheelchair,
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
    c: Tuple[float, float, float],
    step_thresh: float,
    flat_baseline: float,
) -> bool:
    """True if max vertex/centroid excess above ``flat_baseline`` reaches ``step_thresh``."""
    cx = (a[0] + b[0] + c[0]) / 3.0
    cy = (a[1] + b[1] + c[1]) / 3.0
    cz = (a[2] + b[2] + c[2]) / 3.0
    cpy_c = _wheelchair_closest_y(wheelchair, cx, cy, cz)
    if cpy_c is None:
        return False
    raw_cent = abs(float(cy) - cpy_c)
    cent_excess = raw_cent - flat_baseline
    if cent_excess >= step_thresh:
        return True
    if raw_cent >= _STAIR_RAW_HIGH_CM and cent_excess >= _STAIR_RAW_WITH_EXCESS_CM:
        return True

    y_lo = min(a[1], b[1], c[1])
    y_hi = max(a[1], b[1], c[1])
    y_span = y_hi - y_lo
    need_vertices = y_span >= _MIN_Y_SPAN_FOR_VERTEX_PROBE_CM or cent_excess > (
        -step_thresh * float(_VERTEX_NEAR_MISS_FRAC)
    )
    if not need_vertices:
        return False

    max_excess = cent_excess
    for vx, vy, vz in (a, b, c):
        cpy = _wheelchair_closest_y(wheelchair, vx, vy, vz)
        if cpy is None:
            continue
        max_excess = max(max_excess, abs(float(vy) - cpy) - flat_baseline)
    return max_excess >= step_thresh


class AccessibilityDiffService:
    def __init__(self, mode_cache) -> None:
        self._mode_cache = mode_cache
        self._last_recompute_key: Optional[Tuple[Tuple[int, int], int]] = None
        self._feature_enabled: bool = False
        self._overlay_visible: bool = False

    def is_feature_enabled(self) -> bool:
        """Dev-only master switch (``accessibilityDiffShow``). When false, no diff work."""
        return self._feature_enabled

    def _clear_feature_state(self) -> None:
        """Drop meshes — feature turned off."""
        self._last_recompute_key = None
        self._rebuild_usd_meshes([])
        try:
            from younite.payload_orchestrator_core_extension import hide, Priority

            hide(_OVERLAY_ROOT, Priority.LOW, source=_PAYLOAD_ORCH_SOURCE)
        except Exception:
            pass

    def set_feature_enabled(self, enabled: bool) -> None:
        """Dev menu master switch: overlay + diff. Default off."""
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
                print(f"[ACCESS_DIFF] overlay visibility request failed: {exc}")
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2("accessibilityDiffStatus", {"visible": en})
        except Exception:
            pass
        try:
            from younite.usd_viewer_stage_core_extension.services.core_services.world_state_sync_service import (
                get_world_state_sync_service,
            )

            wss = get_world_state_sync_service()
            if wss:
                wss.set("accessibilityDiffOverlayVisible", en)
        except Exception:
            pass

    def set_overlay_visible(self, visible: bool) -> None:
        """Backward-compatible alias for ``set_feature_enabled``."""
        self.set_feature_enabled(visible)

    def _rebuild_usd_meshes(
        self,
        per_cluster_tris: List[
            List[
                Tuple[
                    Tuple[float, float, float],
                    Tuple[float, float, float],
                    Tuple[float, float, float],
                ]
            ]
        ],
    ) -> None:
        """One ``UsdGeomMesh`` per cluster under ``_STAIR_BLOCKS``."""
        try:
            import omni.usd
            from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt
        except Exception as exc:
            print(f"[ACCESS_DIFF] USD import failed: {exc}")
            return

        ctx = omni.usd.get_context()
        stage = ctx.get_stage() if ctx else None
        if not stage:
            return

        root = stage.GetPrimAtPath(_OVERLAY_ROOT)
        if root and root.IsValid():
            stage.RemovePrim(_OVERLAY_ROOT)
        stage.DefinePrim(_OVERLAY_ROOT, "Xform")
        stage.DefinePrim(_STAIR_BLOCKS, "Xform")

        mat_prim = stage.GetPrimAtPath(_MATERIAL_PATH)
        if not mat_prim or not mat_prim.IsValid():
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
            shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.4)
            mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

        lift = float(_Y_LIFT_CM)
        for ci, tris in enumerate(per_cluster_tris):
            if not tris:
                continue
            mesh_path = f"{_STAIR_BLOCKS}/cluster_{ci:04d}"
            mesh_prim = stage.DefinePrim(mesh_path, "Mesh")
            mesh = UsdGeom.Mesh(mesh_prim)
            pts: List[Gf.Vec3f] = []
            f_counts: List[int] = []
            f_indices: List[int] = []
            for tri in tris:
                if len(tri) < 3:
                    continue
                base = len(pts)
                for k in range(3):
                    vx, vy, vz = tri[k]
                    pts.append(Gf.Vec3f(float(vx), float(vy) + lift, float(vz)))
                f_counts.append(3)
                f_indices.extend([base, base + 1, base + 2])
            if len(pts) < 3:
                continue
            pa = mesh.CreatePointsAttr()
            pa.Set(Vt.Vec3fArray([Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in pts]))
            mesh.CreateFaceVertexCountsAttr(Vt.IntArray(f_counts))
            mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(f_indices))
            try:
                mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
            except Exception:
                pass
            try:
                UsdShade.MaterialBindingAPI.Apply(mesh_prim)
                m = UsdShade.Material(stage.GetPrimAtPath(_MATERIAL_PATH))
                if m:
                    UsdShade.MaterialBindingAPI(mesh_prim).Bind(m)
            except Exception:
                pass

    def recompute(self) -> bool:
        if not self._feature_enabled:
            return True
        t0 = time.perf_counter()
        walking, wheelchair = self._mode_cache.get_handles()
        if walking is None or wheelchair is None:
            print("[ACCESS_DIFF] recompute skipped — missing cached handles")
            return False

        try:
            sig = (int(walking.get_mesh_signature()), int(wheelchair.get_mesh_signature()))
        except Exception:
            sig = (0, 0)

        key = (sig, _DIFF_ALG_VERSION)
        if self._last_recompute_key == key:
            return True

        try:
            step_h = float(walking.get_agent_max_step_height())
        except Exception:
            step_h = 40.0
        step_thresh = max(_MIN_STEP_CM, step_h * _STEP_HEIGHT_FACTOR)
        flat_baseline = _sampled_flat_y_offset(walking, wheelchair)

        walking_only: List[
            Tuple[
                Tuple[float, float, float],
                Tuple[float, float, float],
                Tuple[float, float, float],
            ]
        ] = []

        try:
            n_areas = int(walking.get_area_count())
        except Exception:
            n_areas = 0

        for ai in range(n_areas):
            try:
                raw = walking.get_draw_triangles(ai)
            except Exception:
                continue
            pts = list(raw) if raw is not None else []
            n = len(pts)
            if n < 3 or n % 3 != 0:
                continue
            for i in range(0, n, 3):
                a = _xyz(pts[i])
                b = _xyz(pts[i + 1])
                c = _xyz(pts[i + 2])
                if _triangle_is_walking_only_vs_wheelchair(
                    wheelchair, a, b, c, step_thresh, flat_baseline
                ):
                    walking_only.append((a, b, c))

        if not walking_only:
            self._rebuild_usd_meshes([])
            try:
                from younite.payload_orchestrator_core_extension import hide, Priority

                hide(_OVERLAY_ROOT, Priority.LOW, source=_PAYLOAD_ORCH_SOURCE)
            except Exception:
                pass
            self._last_recompute_key = key
            print(
                f"[ACCESS_DIFF] recompute done in {(time.perf_counter()-t0)*1000:.1f}ms — "
                f"0 stair tris (flat Δ p{_FLAT_OFFSET_QUANTILE:.2f}≈{flat_baseline:.1f} cm, step≥{step_thresh:.1f} cm)"
            )
            return True

        tri_count = len(walking_only)
        edge_to_tris: Dict[
            Tuple[Tuple[int, int, int], Tuple[int, int, int]], List[int]
        ] = {}
        for ti, tri in enumerate(walking_only):
            ka = _vkey(*tri[0])
            kb = _vkey(*tri[1])
            kc = _vkey(*tri[2])
            for e in (_edge_key(ka, kb), _edge_key(kb, kc), _edge_key(ka, kc)):
                edge_to_tris.setdefault(e, []).append(ti)

        unassigned: Set[int] = set(range(tri_count))
        cluster_tris_idx: List[List[int]] = []
        while unassigned:
            start = unassigned.pop()
            q: deque[int] = deque([start])
            seen_t: Set[int] = {start}
            comp: List[int] = []
            while q:
                cur = q.popleft()
                comp.append(cur)
                tri = walking_only[cur]
                keys = (_vkey(*tri[0]), _vkey(*tri[1]), _vkey(*tri[2]))
                for e in (
                    _edge_key(keys[0], keys[1]),
                    _edge_key(keys[1], keys[2]),
                    _edge_key(keys[0], keys[2]),
                ):
                    for nb in edge_to_tris.get(e, ()):
                        if nb in seen_t:
                            continue
                        seen_t.add(nb)
                        q.append(nb)
                        unassigned.discard(nb)
            cluster_tris_idx.append(comp)

        mesh_by_cluster: List[
            List[
                Tuple[
                    Tuple[float, float, float],
                    Tuple[float, float, float],
                    Tuple[float, float, float],
                ]
            ]
        ] = []
        cid = 0
        for comp in cluster_tris_idx:
            if len(comp) < _MIN_CLUSTER_TRIS:
                continue
            mesh_by_cluster.append([walking_only[ti] for ti in comp])
            cid += 1

        self._rebuild_usd_meshes(mesh_by_cluster)

        try:
            from younite.payload_orchestrator_core_extension import show_hide, hide, Priority

            if self._overlay_visible:
                show_hide(_OVERLAY_ROOT, True, Priority.MEDIUM, source=_PAYLOAD_ORCH_SOURCE)
            else:
                hide(_OVERLAY_ROOT, Priority.LOW, source=_PAYLOAD_ORCH_SOURCE)
        except Exception:
            pass

        self._last_recompute_key = key
        kept = sum(len(m) for m in mesh_by_cluster)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if len(walking_only) > 150_000:
            print(
                f"[ACCESS_DIFF] WARNING: {len(walking_only)} stair-classified tris — "
                "threshold may be too low; expect slow recompute."
            )
        print(
            f"[ACCESS_DIFF] recompute done in {elapsed_ms:.1f}ms — "
            f"{len(walking_only)} stair tris, {cid} clusters ({kept} tris drawn), "
            f"flat Δ p{_FLAT_OFFSET_QUANTILE:.2f}≈{flat_baseline:.1f} cm"
        )
        return True
