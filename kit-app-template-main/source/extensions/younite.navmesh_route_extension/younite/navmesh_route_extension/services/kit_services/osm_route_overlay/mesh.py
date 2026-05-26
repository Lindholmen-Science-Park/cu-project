"""Session-layer USD mesh + material for the translucent route overlay."""

from __future__ import annotations

import math
from typing import Any, List, Set, Tuple

from .constants import (
    OVERLAY_COLOR,
    OVERLAY_EMISSIVE_GAIN,
    OVERLAY_HOVER_CM,
    OVERLAY_MATERIAL_PATH,
    OVERLAY_MESH_PATH,
    OVERLAY_OPACITY,
    OVERLAY_ROOT,
    OVERLAY_ROUGHNESS,
    OVERLAY_SHADER_PATH,
    OVERLAY_WIDTH_CM,
    VISUAL_EDGE_CLASSES,
)
from .parse_edge import parse_osm_edge


def purge_overlay_prims(stage: Any) -> None:
    try:
        from pxr import Usd

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, session):
            root = stage.GetPrimAtPath(OVERLAY_ROOT)
            if root and root.IsValid():
                try:
                    stage.RemovePrim(OVERLAY_ROOT)
                except Exception:
                    pass
    except Exception:
        pass


def build_mesh_data(
    graph: Any,
    mode: str,
    ox: float,
    oz: float,
) -> Tuple[
    List[Tuple[float, float, float]],
    List[int],
    List[int],
]:
    """Vertices + face arrays for one horizontal quad per visible edge."""
    nodes = getattr(graph, "_nodes", {}) or {}
    adj = getattr(graph, "_adj", {}) or {}
    half_w = OVERLAY_WIDTH_CM * 0.5

    seen: Set[Tuple[str, str]] = set()
    verts: List[Tuple[float, float, float]] = []
    face_counts: List[int] = []
    face_indices: List[int] = []

    for nid, neighbors in adj.items():
        ac = nodes.get(nid)
        if not ac or len(ac) < 3:
            continue
        for e in neighbors:
            pe = parse_osm_edge(e, mode)
            if pe is None:
                continue
            nb, _dist, ecls, _acc = pe
            if ecls not in VISUAL_EDGE_CLASSES:
                continue
            key = (nid, nb) if nid < nb else (nb, nid)
            if key in seen:
                continue
            seen.add(key)
            bc = nodes.get(nb)
            if not bc or len(bc) < 3:
                continue

            ax = float(ac[0]) + ox
            ay = float(ac[1]) + OVERLAY_HOVER_CM
            az = float(ac[2]) + oz
            bx = float(bc[0]) + ox
            by = float(bc[1]) + OVERLAY_HOVER_CM
            bz = float(bc[2]) + oz

            dx = bx - ax
            dz = bz - az
            seg_len = math.sqrt(dx * dx + dz * dz)
            if seg_len < 1.0:
                continue
            rx = dz / seg_len
            rz = -dx / seg_len
            ohx = rx * half_w
            ohz = rz * half_w

            base = len(verts)
            verts.append((ax - ohx, ay, az - ohz))
            verts.append((ax + ohx, ay, az + ohz))
            verts.append((bx + ohx, by, bz + ohz))
            verts.append((bx - ohx, by, bz - ohz))
            face_counts.append(4)
            face_indices.extend((base, base + 1, base + 2, base + 3))

    return verts, face_counts, face_indices


def write_mesh(
    stage: Any,
    verts: List[Tuple[float, float, float]],
    face_counts: List[int],
    face_indices: List[int],
) -> None:
    """Author mesh, PreviewSurface material, and PhysX collision on session."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt

    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, session):
        UsdGeom.Xform.Define(stage, OVERLAY_ROOT)
        mesh = UsdGeom.Mesh.Define(stage, OVERLAY_MESH_PATH)
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*v) for v in verts]))
        mesh.CreateFaceVertexCountsAttr(Vt.IntArray(face_counts))
        mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(face_indices))
        mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        try:
            mesh.CreateDoubleSidedAttr(True)
        except Exception:
            pass
        try:
            mesh.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
        except Exception:
            pass

        UsdGeom.Scope.Define(stage, f"{OVERLAY_ROOT}/Looks")
        material = UsdShade.Material.Define(stage, OVERLAY_MATERIAL_PATH)
        shader = UsdShade.Shader.Define(stage, OVERLAY_SHADER_PATH)
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*OVERLAY_COLOR)
        )
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(
                OVERLAY_COLOR[0] * OVERLAY_EMISSIVE_GAIN,
                OVERLAY_COLOR[1] * OVERLAY_EMISSIVE_GAIN,
                OVERLAY_COLOR[2] * OVERLAY_EMISSIVE_GAIN,
            )
        )
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(OVERLAY_OPACITY))
        shader.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(OVERLAY_ROUGHNESS))
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface"
        )
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

        try:
            UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
            mesh_api = UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim())
            mesh_api.CreateApproximationAttr().Set("none")
        except Exception:
            pass
