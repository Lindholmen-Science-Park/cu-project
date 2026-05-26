"""
Vertex editing service: read mesh vertices, visualise them as PointInstancer dots,
find closest vertex to a world hit, select/highlight, and nudge positions.
"""

from .edit_layer_manager import EditLayerManager, _get_stage

VERTEX_DOTS_ROOT = "/World/VertexEditDots"
MEASURE_LINE_PATH = "/World/VertexMeasureLine"
PROTO_NORMAL_PATH = f"{VERTEX_DOTS_ROOT}/Prototypes/NormalDot"
PROTO_SELECTED_PATH = f"{VERTEX_DOTS_ROOT}/Prototypes/SelectedDot"
MATERIAL_NORMAL_PATH = f"{VERTEX_DOTS_ROOT}/Prototypes/NormalMat"
MATERIAL_SELECTED_PATH = f"{VERTEX_DOTS_ROOT}/Prototypes/SelectedMat"
INSTANCER_PATH = f"{VERTEX_DOTS_ROOT}/Instancer"

DOT_RADIUS_NORMAL = 3.0
DOT_RADIUS_SELECTED = 5.0
COLOR_NORMAL = (0.2, 0.6, 1.0)
COLOR_SELECTED = (1.0, 0.2, 0.2)


def _make_dot_material(stage, mat_path, color):
    from pxr import UsdShade, Sdf, Gf
    mat = UsdShade.Material.Define(stage, mat_path)
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.85)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


class VertexEditService:
    def __init__(self, layer_mgr: EditLayerManager):
        self._layer_mgr = layer_mgr
        self._active_mesh_path = None
        self._world_points = None
        self._local_points = None
        self._local_to_world = None
        self._world_to_local = None
        self._selected_index = None
        self._edited_mesh_paths: set = set()

    @property
    def active_mesh_path(self):
        return self._active_mesh_path

    @property
    def selected_index(self):
        return self._selected_index

    @property
    def has_unsaved_edits(self) -> bool:
        return len(self._edited_mesh_paths) > 0

    # ── Mesh editing ─────────────────────────────────────────────────

    def enter_mesh_edit(self, mesh_prim_path: str) -> dict:
        from pxr import Usd, UsdGeom, Gf

        self._exit_dots_only()

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        prim = stage.GetPrimAtPath(mesh_prim_path)
        if not prim or not prim.IsValid():
            return {"error": f"prim not found: {mesh_prim_path}"}

        mesh = UsdGeom.Mesh(prim)
        if not mesh:
            return {"error": f"not a mesh: {mesh_prim_path}"}

        points_attr = mesh.GetPointsAttr()
        if not points_attr or not points_attr.HasValue():
            return {"error": f"mesh has no points: {mesh_prim_path}"}

        local_points = list(points_attr.Get())
        if not local_points:
            return {"error": f"mesh has empty points: {mesh_prim_path}"}

        xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        local_to_world = xform_cache.GetLocalToWorldTransform(prim)
        world_to_local = local_to_world.GetInverse()

        world_points = []
        for lp in local_points:
            wp = local_to_world.Transform(Gf.Vec3d(lp[0], lp[1], lp[2]))
            world_points.append(wp)

        self._active_mesh_path = mesh_prim_path
        self._local_points = local_points
        self._world_points = world_points
        self._local_to_world = local_to_world
        self._world_to_local = world_to_local
        self._selected_index = None

        self._create_dot_instancer(stage, world_points)

        count = len(world_points)
        print(f"[usd_edit:vertex] Editing mesh {mesh_prim_path} — {count} vertices")
        return {"meshPath": mesh_prim_path, "vertexCount": count}

    def select_closest_vertex(self, world_hit_x: float, world_hit_y: float, world_hit_z: float) -> dict:
        from pxr import Gf

        if not self._world_points:
            return {"error": "no mesh loaded"}

        hit = Gf.Vec3d(world_hit_x, world_hit_y, world_hit_z)
        best_dist = float("inf")
        best_idx = 0

        for i, wp in enumerate(self._world_points):
            d = (wp - hit).GetLength()
            if d < best_dist:
                best_dist = d
                best_idx = i

        self._selected_index = best_idx
        self._update_highlight(best_idx)

        wp = self._world_points[best_idx]
        print(f"[usd_edit:vertex] Selected vertex #{best_idx} (dist={best_dist:.1f})")
        return {
            "vertexIndex": best_idx,
            "x": float(wp[0]),
            "y": float(wp[1]),
            "z": float(wp[2]),
            "distance": float(best_dist),
        }

    def move_vertex(self, index: int, new_x: float, new_y: float, new_z: float) -> dict:
        from pxr import Usd, UsdGeom, Vt, Gf

        if not self._world_points or not self._active_mesh_path:
            return {"error": "no mesh loaded"}
        if index < 0 or index >= len(self._world_points):
            return {"error": f"index out of range: {index}"}

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        new_world = Gf.Vec3d(new_x, new_y, new_z)
        new_local = self._world_to_local.Transform(new_world)

        self._world_points[index] = new_world
        self._local_points[index] = Gf.Vec3f(float(new_local[0]), float(new_local[1]), float(new_local[2]))

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            mesh_prim = stage.GetPrimAtPath(self._active_mesh_path)
            if mesh_prim and mesh_prim.IsValid():
                mesh = UsdGeom.Mesh(mesh_prim)
                mesh.GetPointsAttr().Set(Vt.Vec3fArray(self._local_points))

        self._edited_mesh_paths.add(self._active_mesh_path)
        self._update_dot_positions()

        return {"vertexIndex": index, "x": new_x, "y": new_y, "z": new_z}

    def nudge_vertex(self, index: int, dx: float, dy: float, dz: float) -> dict:
        if not self._world_points or index < 0 or index >= len(self._world_points):
            return {"error": "invalid state or index"}
        wp = self._world_points[index]
        return self.move_vertex(index, float(wp[0]) + dx, float(wp[1]) + dy, float(wp[2]) + dz)

    DRAG_SENSITIVITY = 0.5

    def drag_vertex(self, screen_dx: float, screen_dy: float) -> dict:
        """Move selected vertex based on screen-space pixel deltas.
        Horizontal drag moves along the camera's right vector projected onto XZ.
        Vertical drag moves along world Y."""
        from pxr import Usd, UsdGeom, Gf
        import omni.usd

        if self._selected_index is None or not self._world_points:
            return {"error": "no vertex selected"}
        index = self._selected_index
        if index < 0 or index >= len(self._world_points):
            return {"error": "invalid vertex index"}

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        cam_right_xz = Gf.Vec3d(1, 0, 0)
        try:
            viewport = None
            try:
                from omni.kit.viewport.utility import get_active_viewport
                viewport = get_active_viewport()
            except ImportError:
                pass

            cam_path = None
            if viewport:
                cam_path = viewport.camera_path
            if not cam_path:
                cam_path = "/OmniverseKit_Persp"

            cam_prim = stage.GetPrimAtPath(cam_path)
            if cam_prim and cam_prim.IsValid():
                xf_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
                cam_world = xf_cache.GetLocalToWorldTransform(cam_prim)
                right = Gf.Vec3d(cam_world[0][0], cam_world[0][1], cam_world[0][2])
                right_xz = Gf.Vec3d(right[0], 0, right[2])
                length = right_xz.GetLength()
                if length > 1e-6:
                    cam_right_xz = right_xz / length
        except Exception as e:
            print(f"[usd_edit:vertex] camera lookup fallback: {e}")

        s = self.DRAG_SENSITIVITY
        wp = self._world_points[index]
        new_x = float(wp[0]) + screen_dx * s * cam_right_xz[0]
        new_y = float(wp[1]) - screen_dy * s
        new_z = float(wp[2]) + screen_dx * s * cam_right_xz[2]

        return self.move_vertex(index, new_x, new_y, new_z)

    # ── Save / Reset ─────────────────────────────────────────────────

    def save_edits(self) -> int:
        """Copy session-layer mesh point overrides to the edit sublayer. Returns count."""
        from pxr import Usd, UsdGeom, Vt

        if not self._edited_mesh_paths:
            return 0

        stage = _get_stage()
        if not stage:
            return 0

        edit_layer = self._layer_mgr.ensure_edit_layer()
        if not edit_layer:
            return 0

        session = stage.GetSessionLayer()
        saved = 0

        for mesh_path in list(self._edited_mesh_paths):
            mesh_prim = stage.GetPrimAtPath(mesh_path)
            if not mesh_prim or not mesh_prim.IsValid():
                continue
            mesh = UsdGeom.Mesh(mesh_prim)
            current_points = mesh.GetPointsAttr().Get()
            if not current_points:
                continue

            with Usd.EditContext(stage, Usd.EditTarget(edit_layer)):
                mesh.GetPointsAttr().Set(Vt.Vec3fArray(current_points))

            with Usd.EditContext(stage, Usd.EditTarget(session)):
                mesh_prim.RemoveProperty("points")

            saved += 1

        self._edited_mesh_paths.clear()
        return saved

    def reset_session(self) -> int:
        """Clear session-layer mesh point overrides and refresh dots. Returns count."""
        from pxr import Usd, UsdGeom, Gf

        if not self._edited_mesh_paths:
            return 0

        stage = _get_stage()
        if not stage:
            return 0

        session = stage.GetSessionLayer()
        reset = 0

        for mesh_path in list(self._edited_mesh_paths):
            prim = stage.GetPrimAtPath(mesh_path)
            if prim and prim.IsValid():
                with Usd.EditContext(stage, Usd.EditTarget(session)):
                    prim.RemoveProperty("points")
                reset += 1

        self._edited_mesh_paths.clear()

        if self._active_mesh_path and reset > 0:
            prim = stage.GetPrimAtPath(self._active_mesh_path)
            if prim and prim.IsValid():
                mesh = UsdGeom.Mesh(prim)
                local_points = list(mesh.GetPointsAttr().Get() or [])
                world_points = []
                for lp in local_points:
                    wp = self._local_to_world.Transform(Gf.Vec3d(lp[0], lp[1], lp[2]))
                    world_points.append(wp)
                self._local_points = local_points
                self._world_points = world_points
                self._selected_index = None
                self._update_dot_positions()

        return reset

    # ── Exit / cleanup ───────────────────────────────────────────────

    def _exit_dots_only(self):
        from pxr import Usd, UsdGeom, Vt

        stage = _get_stage()
        if not stage:
            return

        try:
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, Usd.EditTarget(session)):
                root_prim = stage.GetPrimAtPath(VERTEX_DOTS_ROOT)
                if root_prim and root_prim.IsValid():
                    UsdGeom.Imageable(root_prim).MakeInvisible()

                prim = stage.GetPrimAtPath(INSTANCER_PATH)
                if prim and prim.IsValid():
                    UsdGeom.Imageable(prim).MakeInvisible()
                    inst = UsdGeom.PointInstancer(prim)
                    inst.GetPositionsAttr().Set(Vt.Vec3fArray())
                    inst.GetProtoIndicesAttr().Set(Vt.IntArray())
                    inst.GetScalesAttr().Set(Vt.Vec3fArray())
                stage.RemovePrim(VERTEX_DOTS_ROOT)
        except Exception as e:
            print(f"[usd_edit:vertex] dot cleanup error: {e}")

        self._active_mesh_path = None
        self._world_points = None
        self._local_points = None
        self._local_to_world = None
        self._world_to_local = None
        self._selected_index = None

    def exit_edit_mode(self):
        was_active = self._active_mesh_path is not None
        self.clear_measure_line()
        self._exit_dots_only()
        if was_active:
            print("[usd_edit:vertex] Exited edit mode")

    # ── PointInstancer helpers ───────────────────────────────────────

    def _create_dot_instancer(self, stage, world_points):
        from pxr import Usd, UsdGeom, UsdShade, Vt, Gf

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            UsdGeom.Xform.Define(stage, VERTEX_DOTS_ROOT)

            sphere_normal = UsdGeom.Sphere.Define(stage, PROTO_NORMAL_PATH)
            sphere_normal.GetRadiusAttr().Set(DOT_RADIUS_NORMAL)
            sphere_normal.GetDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*COLOR_NORMAL)]))
            mat_normal = _make_dot_material(stage, MATERIAL_NORMAL_PATH, COLOR_NORMAL)
            UsdShade.MaterialBindingAPI.Apply(sphere_normal.GetPrim()).Bind(mat_normal)

            sphere_selected = UsdGeom.Sphere.Define(stage, PROTO_SELECTED_PATH)
            sphere_selected.GetRadiusAttr().Set(DOT_RADIUS_SELECTED)
            sphere_selected.GetDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*COLOR_SELECTED)]))
            mat_selected = _make_dot_material(stage, MATERIAL_SELECTED_PATH, COLOR_SELECTED)
            UsdShade.MaterialBindingAPI.Apply(sphere_selected.GetPrim()).Bind(mat_selected)

            instancer = UsdGeom.PointInstancer.Define(stage, INSTANCER_PATH)
            instancer.CreatePrototypesRel().SetTargets([PROTO_NORMAL_PATH, PROTO_SELECTED_PATH])

            positions = Vt.Vec3fArray([Gf.Vec3f(float(wp[0]), float(wp[1]), float(wp[2])) for wp in world_points])
            indices = Vt.IntArray([0] * len(world_points))
            scales = Vt.Vec3fArray([Gf.Vec3f(1.0, 1.0, 1.0)] * len(world_points))

            instancer.GetPositionsAttr().Set(positions)
            instancer.GetProtoIndicesAttr().Set(indices)
            instancer.GetScalesAttr().Set(scales)

    def _update_highlight(self, selected_idx):
        from pxr import Usd, UsdGeom, Vt
        stage = _get_stage()
        if not stage or not self._world_points:
            return
        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            prim = stage.GetPrimAtPath(INSTANCER_PATH)
            if not prim or not prim.IsValid():
                return
            inst = UsdGeom.PointInstancer(prim)
            indices = [0] * len(self._world_points)
            if 0 <= selected_idx < len(indices):
                indices[selected_idx] = 1
            inst.GetProtoIndicesAttr().Set(Vt.IntArray(indices))

    def _update_dot_positions(self):
        from pxr import Usd, UsdGeom, Vt, Gf
        stage = _get_stage()
        if not stage or not self._world_points:
            return
        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            prim = stage.GetPrimAtPath(INSTANCER_PATH)
            if not prim or not prim.IsValid():
                return
            inst = UsdGeom.PointInstancer(prim)
            positions = Vt.Vec3fArray([Gf.Vec3f(float(wp[0]), float(wp[1]), float(wp[2])) for wp in self._world_points])
            inst.GetPositionsAttr().Set(positions)

    # ── Measure helpers ──────────────────────────────────────────────

    def highlight_multiple(self, indices: list):
        from pxr import Usd, UsdGeom, Vt
        stage = _get_stage()
        if not stage or not self._world_points:
            return
        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            prim = stage.GetPrimAtPath(INSTANCER_PATH)
            if not prim or not prim.IsValid():
                return
            inst = UsdGeom.PointInstancer(prim)
            proto = [0] * len(self._world_points)
            for idx in indices:
                if 0 <= idx < len(proto):
                    proto[idx] = 1
            inst.GetProtoIndicesAttr().Set(Vt.IntArray(proto))

    def draw_measure_line(self, x1, y1, z1, x2, y2, z2):
        from pxr import Usd, UsdGeom, Gf, Vt
        stage = _get_stage()
        if not stage:
            return
        self.clear_measure_line()
        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            curves = UsdGeom.BasisCurves.Define(stage, MEASURE_LINE_PATH)
            curves.CreateTypeAttr("linear")
            curves.CreateCurveVertexCountsAttr([2])
            curves.CreatePointsAttr([
                Gf.Vec3f(float(x1), float(y1), float(z1)),
                Gf.Vec3f(float(x2), float(y2), float(z2)),
            ])
            curves.CreateWidthsAttr([3.0, 3.0])
            curves.GetDisplayColorAttr().Set([Gf.Vec3f(1.0, 0.85, 0.0)])

    def clear_measure_line(self):
        from pxr import Usd, UsdGeom
        stage = _get_stage()
        if not stage:
            return
        prim = stage.GetPrimAtPath(MEASURE_LINE_PATH)
        if prim and prim.IsValid():
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, Usd.EditTarget(session)):
                UsdGeom.Imageable(prim).MakeInvisible()
                stage.RemovePrim(MEASURE_LINE_PATH)
