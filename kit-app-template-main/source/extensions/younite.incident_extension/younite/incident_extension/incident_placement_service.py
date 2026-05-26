"""
Incident placement: visible 3D shape + flat NavMesh area mesh.

The shape is the visual representation (sticks up from ground, clips into it
slightly). The flat mesh underneath carries NavMeshAreaAPI so the baker treats
it as a non-walkable area — same pattern as camera_navmesh_areas.py.

Supports rectangular dimensions (width × depth) and multiple shapes:
  - **cube** (default): UsdGeom.Cube
  - **cone**: UsdGeom.Cone
  - **torus**: procedural torus mesh
"""

import math
import time
from typing import Optional

_NAV_LAYER_FILENAME = "navigation_layer.usda"
INCIDENTS_PARENT_PATH = "/World/Incidents"
DEFAULT_WIDTH = 100.0   # 1m
DEFAULT_DEPTH = 100.0   # 1m
DEFAULT_HEIGHT = 150.0  # 1.5m
INCIDENT_AREA_NAME = "incident_blocked"
GROUND_OFFSET = 0.5
VALID_SHAPES = ("cube", "cone", "torus")


def _find_nav_layer(stage):
    from pxr import Sdf
    root_layer = stage.GetRootLayer()
    for sub_path in root_layer.subLayerPaths:
        if _NAV_LAYER_FILENAME in sub_path:
            layer = Sdf.Layer.FindRelativeToLayer(root_layer, sub_path)
            if layer:
                return layer
    return None


def _ensure_incident_material(stage, layer):
    from pxr import Gf, Sdf, Usd, UsdShade

    mat_path = f"{INCIDENTS_PARENT_PATH}/IncidentMaterial"
    prim = stage.GetPrimAtPath(mat_path)
    if prim and prim.IsValid():
        mat = UsdShade.Material(prim)
        if mat:
            return mat

    with Usd.EditContext(stage, layer):
        mat = UsdShade.Material.Define(stage, mat_path)
        shader = UsdShade.Shader.Define(stage, f"{mat_path}/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(0.9, 0.35, 0.0))
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(0.9 * 1.6, 0.35 * 1.6, 0.0))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.55)
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _create_torus_mesh(stage, path, major_r, minor_r, segments=24, sides=12):
    """Create a torus mesh prim at *path*. Ring lies in the XZ plane."""
    from pxr import Gf, UsdGeom

    points = []
    for i in range(segments):
        theta = 2.0 * math.pi * i / segments
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        for j in range(sides):
            phi = 2.0 * math.pi * j / sides
            cos_p, sin_p = math.cos(phi), math.sin(phi)
            x = (major_r + minor_r * cos_p) * cos_t
            z = (major_r + minor_r * cos_p) * sin_t
            y = minor_r * sin_p
            points.append(Gf.Vec3f(x, y, z))

    fvc, fvi = [], []
    for i in range(segments):
        ni = (i + 1) % segments
        for j in range(sides):
            nj = (j + 1) % sides
            fvc.append(4)
            fvi.extend([
                i * sides + j,
                ni * sides + j,
                ni * sides + nj,
                i * sides + nj,
            ])

    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr().Set(points)
    mesh.CreateFaceVertexCountsAttr().Set(fvc)
    mesh.CreateFaceVertexIndicesAttr().Set(fvi)
    mesh.CreateSubdivisionSchemeAttr().Set("none")
    return mesh


def _circular_area(radius, n_sides=16, area_y=GROUND_OFFSET):
    """Generate a flat circular fan mesh (points, fvc, fvi, normals)."""
    from pxr import Gf

    pts = []
    for i in range(n_sides):
        a = 2.0 * math.pi * i / n_sides
        pts.append(Gf.Vec3f(radius * math.cos(a), area_y, radius * math.sin(a)))
    center_idx = n_sides
    pts.append(Gf.Vec3f(0, area_y, 0))

    fvc = [3] * n_sides
    fvi = []
    for i in range(n_sides):
        fvi.extend([i, center_idx, (i + 1) % n_sides])

    normals = [Gf.Vec3f(0, 1, 0)] * (n_sides * 3)
    return pts, fvc, fvi, normals


def remove_all_incidents() -> int:
    """Remove all incident prims under /World/Incidents from the nav layer.

    Returns the number of incident groups removed.
    """
    try:
        import omni.usd
        from pxr import Sdf, Usd

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return 0

        parent = stage.GetPrimAtPath(INCIDENTS_PARENT_PATH)
        if not parent or not parent.IsValid():
            return 0

        nav_layer = _find_nav_layer(stage) or stage.GetRootLayer()
        children = [c.GetPath().pathString for c in parent.GetChildren()]
        count = 0

        with Usd.EditContext(stage, nav_layer):
            for path in children:
                stage.RemovePrim(path)
                count += 1
            stage.RemovePrim(INCIDENTS_PARENT_PATH)

        # Clean up any stale specs on the root layer (same pattern as camera areas)
        root_layer = stage.GetRootLayer()
        if root_layer and root_layer != nav_layer:
            stale = root_layer.GetPrimAtPath(INCIDENTS_PARENT_PATH)
            if stale:
                p = stale.nameParent
                if p:
                    del p.nameChildren[stale.name]

        print(f"[INCIDENT] Removed {count} incidents")
        return count
    except Exception as e:
        print(f"[INCIDENT] remove_all_incidents error: {e}")
        import traceback
        traceback.print_exc()
        return 0


def remove_single_incident(incident_path: str) -> bool:
    """Remove a single incident prim by its full path.

    Returns True if the prim was found and removed.
    """
    try:
        import omni.usd
        from pxr import Sdf, Usd

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return False

        prim = stage.GetPrimAtPath(incident_path)
        if not prim or not prim.IsValid():
            print(f"[INCIDENT] Prim not found for removal: {incident_path}")
            return False

        nav_layer = _find_nav_layer(stage) or stage.GetRootLayer()

        with Usd.EditContext(stage, nav_layer):
            stage.RemovePrim(incident_path)

        root_layer = stage.GetRootLayer()
        if root_layer and root_layer != nav_layer:
            stale = root_layer.GetPrimAtPath(incident_path)
            if stale:
                p = stale.nameParent
                if p and stale.name in p.nameChildren:
                    del p.nameChildren[stale.name]

        print(f"[INCIDENT] Removed single incident: {incident_path}")
        return True
    except Exception as e:
        print(f"[INCIDENT] remove_single_incident error: {e}")
        import traceback
        traceback.print_exc()
        return False


class IncidentPlacementService:
    """Place incident: visible box + flat NavMesh area mesh underneath."""

    def __init__(self):
        self._parent_path = INCIDENTS_PARENT_PATH

    def place_incident(
        self,
        world_pos: tuple,
        label: Optional[str] = None,
        normal: Optional[tuple] = None,
        width: Optional[float] = None,
        depth: Optional[float] = None,
        height: Optional[float] = None,
        shape: Optional[str] = None,
    ) -> Optional[str]:
        try:
            import omni.usd
            from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdPhysics

            stage = omni.usd.get_context().get_stage()
            if not stage:
                print("[INCIDENT] No stage available")
                return None

            nav_layer = _find_nav_layer(stage)
            if not nav_layer:
                print("[INCIDENT] Navigation sublayer not found, falling back to root layer")
                nav_layer = stage.GetRootLayer()

            w = float(width) if width else DEFAULT_WIDTH
            d = float(depth) if depth else DEFAULT_DEPTH
            h = float(height) if height else DEFAULT_HEIGHT
            shape_type = (shape or "cube").strip().lower()
            if shape_type not in VALID_SHAPES:
                shape_type = "cube"

            label_str = str(label) if label else "Incident"
            incident_name = f"Incident_{int(time.time() * 1000)}"
            incident_path = f"{self._parent_path}/{incident_name}"
            vis_path = f"{incident_path}/Shape"
            area_path = f"{incident_path}/Area"

            material = _ensure_incident_material(stage, nav_layer)

            cx, cy, cz = float(world_pos[0]), float(world_pos[1]), float(world_pos[2])
            half_w = w / 2.0
            half_d = d / 2.0

            with Usd.EditContext(stage, nav_layer):
                incidents_root = stage.GetPrimAtPath(self._parent_path)
                if not incidents_root or not incidents_root.IsValid():
                    stage.DefinePrim(self._parent_path, "Xform")

                stage.DefinePrim(incident_path, "Xform")
                xform = UsdGeom.Xformable(stage.GetPrimAtPath(incident_path))
                xform.ClearXformOpOrder()
                xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                    Gf.Vec3d(cx, cy, cz))
                stage.GetPrimAtPath(incident_path).CreateAttribute(
                    "incident:label", Sdf.ValueTypeNames.String).Set(label_str)

                # ── Visual shape ──
                is_round = shape_type in ("cone", "torus")
                footprint_radius = max(w, d) / 2.0

                if shape_type == "cube":
                    cube = UsdGeom.Cube.Define(stage, vis_path)
                    cube.GetSizeAttr().Set(1.0)
                    vis_xform = UsdGeom.Xformable(cube)
                    vis_xform.ClearXformOpOrder()
                    vis_xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                        Gf.Vec3d(0, h * 0.3, 0))
                    vis_xform.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(
                        Gf.Vec3d(w, h, d))

                elif shape_type == "cone":
                    cone = UsdGeom.Cone.Define(stage, vis_path)
                    cone.CreateRadiusAttr().Set(float(footprint_radius))
                    cone.CreateHeightAttr().Set(float(h))
                    cone.CreateAxisAttr().Set("Y")
                    vis_xform = UsdGeom.Xformable(cone)
                    vis_xform.ClearXformOpOrder()
                    vis_xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                        Gf.Vec3d(0, h * 0.5, 0))

                elif shape_type == "torus":
                    major_r = footprint_radius * 0.65
                    minor_r = footprint_radius * 0.35
                    torus_mesh = _create_torus_mesh(
                        stage, vis_path, major_r, minor_r)
                    vis_xform = UsdGeom.Xformable(torus_mesh)
                    vis_xform.ClearXformOpOrder()
                    vis_xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                        Gf.Vec3d(0, minor_r + 2.0, 0))

                vis_prim = stage.GetPrimAtPath(vis_path)
                if vis_prim and vis_prim.IsValid():
                    UsdShade.MaterialBindingAPI.Apply(vis_prim)
                    UsdShade.MaterialBindingAPI(vis_prim).Bind(material)
                    UsdPhysics.CollisionAPI.Apply(vis_prim)

                # ── Flat NavMesh area mesh ──
                if is_round:
                    points, fvc, fvi, normals = _circular_area(
                        footprint_radius, n_sides=16)
                else:
                    area_y = GROUND_OFFSET
                    points = [
                        Gf.Vec3f(-half_w, area_y, -half_d),
                        Gf.Vec3f(half_w, area_y, -half_d),
                        Gf.Vec3f(half_w, area_y, half_d),
                        Gf.Vec3f(-half_w, area_y, half_d),
                        Gf.Vec3f(0, area_y, 0),
                    ]
                    center_idx = 4
                    fvc = [3, 3, 3, 3]
                    fvi = [
                        0, center_idx, 1,
                        1, center_idx, 2,
                        2, center_idx, 3,
                        3, center_idx, 0,
                    ]
                    normals = [Gf.Vec3f(0, 1, 0)] * len(fvi)

                area_prim = stage.DefinePrim(area_path, "Mesh")
                mesh = UsdGeom.Mesh(area_prim)
                mesh.CreatePointsAttr().Set(points)
                mesh.CreateFaceVertexCountsAttr().Set(fvc)
                mesh.CreateFaceVertexIndicesAttr().Set(fvi)
                mesh.CreateNormalsAttr().Set(normals)
                mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
                mesh.CreateDoubleSidedAttr().Set(True)
                mesh.CreateSubdivisionSchemeAttr().Set("none")

                UsdShade.MaterialBindingAPI.Apply(area_prim)
                UsdShade.MaterialBindingAPI(area_prim).Bind(material)

                schemas = Sdf.TokenListOp()
                schemas.prependedItems = ["MaterialBindingAPI", "NavMeshAreaAPI"]
                area_prim.SetMetadata("apiSchemas", schemas)
                area_prim.CreateAttribute("nav:area", Sdf.ValueTypeNames.String).Set(INCIDENT_AREA_NAME)

            from younite.payload_orchestrator_core_extension import show, Priority
            show(self._parent_path, Priority.HIGH, source="incident")
            show(vis_path, Priority.HIGH, source="incident")

            print(f"[INCIDENT] Created {shape_type} at {incident_path} "
                  f"(area={INCIDENT_AREA_NAME}, {w:.0f}x{d:.0f}x{h:.0f})")
            return incident_path
        except Exception as e:
            print(f"[INCIDENT] Error creating incident: {e}")
            import traceback
            traceback.print_exc()
            return None
