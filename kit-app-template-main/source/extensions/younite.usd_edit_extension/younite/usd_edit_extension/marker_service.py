"""
Marker service: create, visualise, select and nudge leaf Xform marker prims.

Markers are empty UsdGeom.Xform prims used as location/reference points
(e.g. spawn points, exit points, restroom markers).  New markers are written
directly to a chosen sublayer; position nudges go either to the shared edit
sublayer (usd_edits.usda) or back to the marker's original/defining layer.
"""

import os

from .edit_layer_manager import EditLayerManager, _get_stage

MARKER_DOTS_ROOT = "/World/MarkerEditDots"
DIRECTION_LINE_PATH = "/World/MarkerDirectionLine"
PROTO_NORMAL_PATH = f"{MARKER_DOTS_ROOT}/Prototypes/NormalDot"
PROTO_SELECTED_PATH = f"{MARKER_DOTS_ROOT}/Prototypes/SelectedDot"
MATERIAL_NORMAL_PATH = f"{MARKER_DOTS_ROOT}/Prototypes/NormalMat"
MATERIAL_SELECTED_PATH = f"{MARKER_DOTS_ROOT}/Prototypes/SelectedMat"
INSTANCER_PATH = f"{MARKER_DOTS_ROOT}/Instancer"

DOT_RADIUS_NORMAL = 5.0
DOT_RADIUS_SELECTED = 7.0
COLOR_NORMAL = (0.2, 0.9, 0.3)
COLOR_SELECTED = (1.0, 0.2, 0.2)
DIRECTION_LINE_LENGTH = 250.0  # 2.5 m
DIRECTION_LINE_WIDTH = 4.0
DIRECTION_LINE_COLOR = (1.0, 0.85, 0.0)  # gold/yellow


def _gf_rotation_from_extracted_matrix3d(m3):
    """Build ``Gf.Rotation`` from ``Gf.Matrix3d`` without ``Rotation(Matrix3d)``.

    Some Kit / USD Python builds omit the ``Gf.Rotation(Matrix3d)`` binding
    (signature error at runtime).  We convert via a standard orthogonal-matrix
    → quaternion (Shepperd / trace) path, then ``Gf.Rotation(Gf.Quatd)``.
    """
    import math
    from pxr import Gf

    r00, r01, r02 = float(m3[0][0]), float(m3[0][1]), float(m3[0][2])
    r10, r11, r12 = float(m3[1][0]), float(m3[1][1]), float(m3[1][2])
    r20, r21, r22 = float(m3[2][0]), float(m3[2][1]), float(m3[2][2])

    trace = r00 + r11 + r22
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        qw = 0.25 / s
        qx = (r21 - r12) * s
        qy = (r02 - r20) * s
        qz = (r10 - r01) * s
    elif r00 > r11 and r00 > r22:
        s = 2.0 * math.sqrt(max(0.0, 1.0 + r00 - r11 - r22))
        if s < 1e-8:
            return Gf.Rotation(Gf.Quatd(1.0, Gf.Vec3d(0.0, 0.0, 0.0)))
        qw = (r21 - r12) / s
        qx = 0.25 * s
        qy = (r01 + r10) / s
        qz = (r02 + r20) / s
    elif r11 > r22:
        s = 2.0 * math.sqrt(max(0.0, 1.0 + r11 - r00 - r22))
        if s < 1e-8:
            return Gf.Rotation(Gf.Quatd(1.0, Gf.Vec3d(0.0, 0.0, 0.0)))
        qw = (r02 - r20) / s
        qx = (r01 + r10) / s
        qy = 0.25 * s
        qz = (r12 + r21) / s
    else:
        s = 2.0 * math.sqrt(max(0.0, 1.0 + r22 - r00 - r11))
        if s < 1e-8:
            return Gf.Rotation(Gf.Quatd(1.0, Gf.Vec3d(0.0, 0.0, 0.0)))
        qw = (r10 - r01) / s
        qx = (r02 + r20) / s
        qy = (r12 + r21) / s
        qz = 0.25 * s

    n = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
    if n < 1e-12:
        return Gf.Rotation(Gf.Quatd(1.0, Gf.Vec3d(0.0, 0.0, 0.0)))
    qw, qx, qy, qz = qw / n, qx / n, qy / n, qz / n
    return Gf.Rotation(Gf.Quatd(qw, Gf.Vec3d(qx, qy, qz)))


def _jf(v: float) -> float:
    """JSON-friendly float: drop -0.0 / float noise for tiny magnitudes."""
    x = float(v)
    if abs(x) < 1e-9:
        return 0.0
    return x


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


class MarkerService:
    def __init__(self, layer_mgr: EditLayerManager):
        self._layer_mgr = layer_mgr
        self._armed_sublayer = None
        self._armed_name = None
        self._show_active = False
        self._leaf_markers = []
        self._selected_index = None
        self._selected_prim_path = None
        self._edited_marker_paths: set = set()
        # iconGroup-attached prims (e.g. spatial_sound_NN, video_360_NN) we
        # have hidden via the Payload Orchestrator while "Show Markers" is on.
        # Restored when show is turned off or marker mode exits, so headphones
        # / VR goggles / ... reappear for normal users.
        self._hidden_icon_group_paths: set = set()

    # ── Sublayer listing ─────────────────────────────────────────────

    def list_active_sublayers(self) -> list:
        from pxr import Sdf

        stage = _get_stage()
        if not stage:
            return []

        root_layer = stage.GetRootLayer()
        result = []
        for sub_path in root_layer.subLayerPaths:
            resolved = root_layer.ComputeAbsolutePath(sub_path)
            layer = Sdf.Layer.Find(resolved)
            if not layer:
                continue
            display = os.path.basename(layer.identifier)
            if display.endswith(".usda") or display.endswith(".usd"):
                display = display.rsplit(".", 1)[0]
            result.append({
                "identifier": layer.identifier,
                "displayName": display,
            })
        return result

    # ── Placement arming ─────────────────────────────────────────────

    def arm_placement(self, sublayer_identifier: str, marker_name: str):
        self._armed_sublayer = sublayer_identifier
        self._armed_name = marker_name
        print(f"[usd_edit:marker] Armed placement: name={marker_name} layer={sublayer_identifier}")

    @property
    def is_armed(self) -> bool:
        return self._armed_sublayer is not None and self._armed_name is not None

    def disarm(self):
        self._armed_sublayer = None
        self._armed_name = None

    # ── Create marker ────────────────────────────────────────────────

    def create_marker_at(self, wx: float, wy: float, wz: float) -> dict:
        from pxr import Usd, UsdGeom, Gf, Sdf

        if not self.is_armed:
            return {"error": "placement not armed"}

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        layer = Sdf.Layer.Find(self._armed_sublayer)
        if not layer:
            resolved = stage.GetRootLayer().ComputeAbsolutePath(self._armed_sublayer)
            layer = Sdf.Layer.Find(resolved)
        if not layer:
            return {"error": f"sublayer not found: {self._armed_sublayer}"}

        name = self._armed_name.strip().replace(" ", "_")
        if not name:
            return {"error": "empty marker name"}

        prim_path = f"/World/{name}"
        existing = stage.GetPrimAtPath(prim_path)
        if existing and existing.IsValid():
            return {"error": f"prim already exists: {prim_path}"}

        with Usd.EditContext(stage, Usd.EditTarget(layer)):
            world_prim = stage.GetPrimAtPath("/World")
            if not world_prim or not world_prim.IsValid():
                world_prim = stage.OverridePrim("/World")

            xform = UsdGeom.Xform.Define(stage, prim_path)
            xform.AddTranslateOp().Set(Gf.Vec3d(wx, wy, wz))
            xform.AddRotateXYZOp().Set(Gf.Vec3d(0, 0, 0))
            xform.AddScaleOp().Set(Gf.Vec3d(1, 1, 1))

        layer.Save()

        sublayer_name = os.path.basename(layer.identifier)
        print(f"[usd_edit:marker] Created marker '{name}' at ({wx:.1f}, {wy:.1f}, {wz:.1f}) in {sublayer_name}")

        self.disarm()

        if self._show_active:
            self._refresh_dots()

        return {
            "primPath": prim_path,
            "x": float(wx),
            "y": float(wy),
            "z": float(wz),
            "sublayer": sublayer_name,
        }

    # ── Layer detection ─────────────────────────────────────────────

    @staticmethod
    def _find_defining_layer(prim):
        """Return the strongest layer that has a def/over spec for *prim*.

        We want the layer where the prim was originally **defined** (a `def`
        spec), not just any `over` higher in composition. Otherwise an
        ``over`` written elsewhere (e.g. an empty placeholder in
        ``usd_edits.usda`` or a stray override in ``main_scene.usda``) would
        win and the panel would mis-report the source layer + nudges with
        ``Edit original layer`` would target the wrong file.
        """
        from pxr import Sdf

        # 1) Strongest non-anonymous layer that contains a `def` spec.
        for spec in prim.GetPrimStack():
            layer = spec.layer
            if not layer or layer.anonymous:
                continue
            if spec.specifier == Sdf.SpecifierDef:
                return layer

        # 2) Fallback: strongest non-anonymous layer of any specifier.
        for spec in prim.GetPrimStack():
            layer = spec.layer
            if layer and not layer.anonymous:
                return layer
        return None

    def _strip_stronger_rotation_opinions(self, prim, target_layer) -> None:
        """Remove ``xformOp:rotateXYZ`` opinions in any layer stronger than *target_layer*.

        Used by ``nudge_marker_rotate`` when ``edit_original=True``. Without
        this, an opinion left in ``usd_edits.usda`` (or session) from an
        earlier ``Edit original = OFF`` nudge silently shadows our write to
        the canonical layer, and the user sees the rotation freeze after the
        first click despite the log saying we wrote a new value.
        """
        from pxr import Sdf

        stage = _get_stage()
        if not stage:
            return
        prim_stack = prim.GetPrimStack()
        if not prim_stack:
            return

        target_id = target_layer.identifier if target_layer else None
        cleared = 0
        for spec in prim_stack:
            layer = spec.layer
            if not layer:
                continue
            if target_id is not None and layer.identifier == target_id:
                # Reached the target — anything further is weaker, no-op.
                break
            prim_spec = layer.GetPrimAtPath(Sdf.Path(prim.GetPath()))
            if not prim_spec:
                continue
            attr_spec = prim_spec.attributes.get("xformOp:rotateXYZ")
            if attr_spec is None:
                continue
            try:
                prim_spec.RemoveProperty(attr_spec)
                cleared += 1
                if not layer.anonymous:
                    try:
                        layer.Save()
                    except Exception:
                        pass
            except Exception as exc:
                print(f"[usd_edit:marker] could not strip rotation on {layer.identifier}: {exc}")
        if cleared:
            print(f"[usd_edit:marker] stripped {cleared} stronger rotation opinion(s) before writing to {self._layer_display_name(target_layer)}")

    @staticmethod
    def _layer_display_name(layer) -> str:
        if not layer:
            return ""
        name = os.path.basename(layer.identifier)
        if name.endswith(".usda") or name.endswith(".usd"):
            name = name.rsplit(".", 1)[0]
        return name

    @staticmethod
    def _world_translation_for_prim(prim) -> tuple:
        """Return (x, y, z) world translation for an Xformable prim."""
        from pxr import UsdGeom

        xformable = UsdGeom.Xformable(prim)
        try:
            world_m = xformable.ComputeLocalToWorldTransform(0)
            t = world_m.ExtractTranslation()
            return float(t[0]), float(t[1]), float(t[2])
        except Exception:
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    val = op.Get()
                    if val is not None:
                        return float(val[0]), float(val[1]), float(val[2])
            return 0.0, 0.0, 0.0

    # ── Leaf marker scanning ─────────────────────────────────────────

    def _load_icon_group_patterns(self) -> list:
        """Read every ``iconGroup.primNamePattern`` from interactions.json.

        Comma-separated patterns (e.g. ``coin_*,exit_point_*``) are split into
        separate fnmatch globs so marker mode matches each prim name correctly.

        These Xforms (e.g. ``spatial_sound_*``, ``video_360_*``) are authored
        as empty markers in their respective sublayers, but the interactions
        extension attaches a payload (headphones / VR goggles / ...) plus an
        invisible ``Collider`` child via session-layer override at runtime.
        That makes them no longer "leaf" Xforms in the composed stage, so the
        plain leaf scan below would skip them — even though for editing they
        absolutely behave like markers (you want to see the dot + arrow at
        their authored XYZ and rotate them to face the player).

        Returns an empty list on any error so callers fall back to the
        classic leaf-only detection.
        """
        import json

        stage = _get_stage()
        if not stage:
            return []
        root_layer = stage.GetRootLayer()
        if not root_layer or not root_layer.realPath:
            return []
        # source/data/scenes/<root>.usda → source/data/interactions.json
        scenes_dir = os.path.dirname(root_layer.realPath)
        data_dir = os.path.dirname(scenes_dir)
        interactions_path = os.path.join(data_dir, "interactions.json")
        if not os.path.isfile(interactions_path):
            return []

        try:
            with open(interactions_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as exc:
            print(f"[usd_edit:marker] could not read interactions.json: {exc}")
            return []

        entries = (
            cfg.get("interactionPoints")
            or cfg.get("interactions")
            or cfg.get("entries")
            or []
        )
        patterns: list = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("interactionType") != "iconGroup":
                continue
            pat = str(entry.get("primNamePattern") or "").strip()
            if not pat:
                continue
            # ``coins_loader`` / ``interactions.json`` may use comma-separated
            # globs (e.g. ``coin_*,exit_point_*``). Each segment must be its own
            # fnmatch pattern — a single string with a comma matches nothing.
            for segment in (s.strip() for s in pat.split(",")):
                if segment and segment not in patterns:
                    patterns.append(segment)
        return patterns

    def _find_nav_shortcut_markers(self) -> list:
        """Leaf Xform nodes under /World/NavShortcuts (elevator floor points, etc.).

        These are nested two levels below /World, so the direct-child scan in
        ``find_leaf_markers`` never sees them.  Uses world translation for dot
        placement (same rule as ``shortcut_router.usd_scan``).
        """
        from pxr import Usd, UsdGeom, Gf

        stage = _get_stage()
        if not stage:
            return []

        root = stage.GetPrimAtPath("/World/NavShortcuts")
        if not root or not root.IsValid():
            return []

        markers = []
        for prim in Usd.PrimRange(root):
            if not prim.IsValid() or prim == root:
                continue
            if not prim.IsA(UsdGeom.Xformable):
                continue
            xform_children = [
                c for c in prim.GetChildren() if c.IsA(UsdGeom.Xformable)
            ]
            if xform_children:
                continue

            xformable = UsdGeom.Xformable(prim)
            translate = Gf.Vec3d(0, 0, 0)
            rotate = Gf.Vec3d(0, 0, 0)
            for op in xformable.GetOrderedXformOps():
                op_type = op.GetOpType()
                val = op.Get()
                if val is None:
                    continue
                if op_type == UsdGeom.XformOp.TypeTranslate:
                    translate = Gf.Vec3d(val)
                elif op_type == UsdGeom.XformOp.TypeRotateXYZ:
                    rotate = Gf.Vec3d(val)

            wx, wy, wz = self._world_translation_for_prim(prim)

            defining_layer = self._find_defining_layer(prim)
            markers.append({
                "primPath": str(prim.GetPath()),
                "name": prim.GetName(),
                "x": wx,
                "y": wy,
                "z": wz,
                "rotX": float(rotate[0]),
                "rotY": float(rotate[1]),
                "rotZ": float(rotate[2]),
                "layerIdentifier": defining_layer.identifier if defining_layer else "",
                "layerDisplayName": self._layer_display_name(defining_layer),
                "isIconGroup": False,
                "isNavShortcut": True,
            })
        return markers

    def find_leaf_markers(self) -> list:
        import fnmatch
        from pxr import UsdGeom, Gf

        stage = _get_stage()
        if not stage:
            return []

        world = stage.GetPrimAtPath("/World")
        if not world or not world.IsValid():
            return []

        icon_group_patterns = self._load_icon_group_patterns()

        markers = []
        seen_paths = set()
        icon_group_count = 0
        leaf_count = 0
        for child in world.GetChildren():
            if not child.IsA(UsdGeom.Xform):
                continue
            if child.IsA(UsdGeom.Mesh) or child.IsA(UsdGeom.Camera):
                continue

            # Treat as a marker if either:
            #   (a) it's a true leaf Xform (no children at all), OR
            #   (b) its leaf name matches an iconGroup primNamePattern from
            #       interactions.json. iconGroups (spatial_sound_*, video_360_*,
            #       videobook_*, ...) attach a payload + Collider at runtime,
            #       so the prim has children in the composed stage but was
            #       authored as an empty marker.
            is_leaf = len(child.GetChildren()) == 0
            is_icon_group = any(
                fnmatch.fnmatch(child.GetName(), pat) for pat in icon_group_patterns
            )
            if not is_leaf and not is_icon_group:
                continue

            xformable = UsdGeom.Xformable(child)
            # Tagged below; collected here so we can pass through to the marker dict.
            _marker_is_icon_group = is_icon_group and not is_leaf
            if _marker_is_icon_group:
                icon_group_count += 1
            else:
                leaf_count += 1
            translate = Gf.Vec3d(0, 0, 0)
            rotate = Gf.Vec3d(0, 0, 0)
            for op in xformable.GetOrderedXformOps():
                op_type = op.GetOpType()
                val = op.Get()
                if val is None:
                    continue
                if op_type == UsdGeom.XformOp.TypeTranslate:
                    translate = Gf.Vec3d(val)
                elif op_type == UsdGeom.XformOp.TypeRotateXYZ:
                    rotate = Gf.Vec3d(val)

            defining_layer = self._find_defining_layer(child)
            prim_path = str(child.GetPath())
            seen_paths.add(prim_path)
            markers.append({
                "primPath": prim_path,
                "name": child.GetName(),
                "x": float(translate[0]),
                "y": float(translate[1]),
                "z": float(translate[2]),
                "rotX": float(rotate[0]),
                "rotY": float(rotate[1]),
                "rotZ": float(rotate[2]),
                "layerIdentifier": defining_layer.identifier if defining_layer else "",
                "layerDisplayName": self._layer_display_name(defining_layer),
                "isIconGroup": _marker_is_icon_group,
                "isNavShortcut": False,
            })

        nav_shortcut_count = 0
        for m in self._find_nav_shortcut_markers():
            if m["primPath"] in seen_paths:
                continue
            seen_paths.add(m["primPath"])
            markers.append(m)
            nav_shortcut_count += 1

        if nav_shortcut_count:
            print(
                f"[usd_edit:marker] Included {nav_shortcut_count} NavShortcuts floor node(s)"
            )

        self._leaf_markers = markers
        return markers

    # ── iconGroup model hide/restore ─────────────────────────────────

    def _hide_icon_group_models(self, markers: list) -> None:
        """Hide payload models attached to iconGroup-managed markers.

        The headphones / VR-goggles model fully envelops the marker XYZ, so
        the marker dot is otherwise invisible inside the mesh. We hide the
        whole iconGroup Xform (which propagates invisibility to the Collider
        + payload children) while ``Show Markers`` is on, then restore on
        exit. Routed through the Payload Orchestrator per project rules.

        We also clear any stale session-layer ``xformOp:rotateXYZ`` opinion
        the interactions extension's icon spin loop wrote before we hid the
        prim. Without this, that pinned session opinion silently wins over
        the canonical layer (and over ``usd_edits.usda``), so every nudge
        appears to "stick once and freeze" — we keep writing new values to
        the right layer but the composed rotation never moves off the
        last spin sample.
        """
        try:
            from younite.payload_orchestrator_core_extension import hide, Priority
        except Exception as exc:
            print(f"[usd_edit:marker] payload orchestrator unavailable: {exc}")
            return

        attempted = 0
        accepted = 0
        for m in markers:
            if not m.get("isIconGroup"):
                continue
            path = m["primPath"]
            if path in self._hidden_icon_group_paths:
                continue
            attempted += 1
            if hide(path, Priority.HIGH, source="usd_edit:marker"):
                self._hidden_icon_group_paths.add(path)
                accepted += 1

        # Clear stale session-layer rotation opinions for every iconGroup
        # marker we manage (whether or not we just hid it now — defensive).
        self._clear_session_rotation_opinions(markers)

    def _clear_session_rotation_opinions(self, markers: list) -> None:
        """Drop session-layer ``xformOp:rotateXYZ`` opinions on iconGroup prims.

        Composes from the next-strongest layer afterwards (usd_edits.usda or
        the canonical sublayer), so subsequent reads in
        ``nudge_marker_rotate`` see the real authored value, not the last
        sample written by the spin loop.
        """
        from pxr import Sdf

        stage = _get_stage()
        if not stage:
            return
        session = stage.GetSessionLayer()
        if not session:
            return

        cleared = 0
        for m in markers:
            if not m.get("isIconGroup"):
                continue
            path = m["primPath"]
            prim_spec = session.GetPrimAtPath(Sdf.Path(path))
            if not prim_spec:
                continue
            attr_spec = prim_spec.attributes.get("xformOp:rotateXYZ")
            if attr_spec is None:
                continue
            try:
                prim_spec.RemoveProperty(attr_spec)
                cleared += 1
            except Exception as exc:
                print(f"[usd_edit:marker] could not clear session rotation on {path}: {exc}")
        if cleared:
            print(f"[usd_edit:marker] cleared {cleared} stale session-layer rotation opinion(s)")

    def _restore_icon_group_models(self) -> None:
        """Re-show every iconGroup model we hid in this session."""
        if not self._hidden_icon_group_paths:
            return
        try:
            from younite.payload_orchestrator_core_extension import show, Priority
        except Exception as exc:
            print(f"[usd_edit:marker] payload orchestrator unavailable: {exc}")
            self._hidden_icon_group_paths.clear()
            return

        for path in list(self._hidden_icon_group_paths):
            show(path, Priority.HIGH, source="usd_edit:marker")
        self._hidden_icon_group_paths.clear()

    # ── Show/hide dots ───────────────────────────────────────────────

    def show_markers(self, visible: bool) -> list:
        self._show_active = visible
        if visible:
            markers = self.find_leaf_markers()
            self._create_dot_instancer(markers)
            self._hide_icon_group_models(markers)
            return markers
        else:
            self._clear_direction_line()
            self._remove_dots()
            self._restore_icon_group_models()
            self._selected_index = None
            self._selected_prim_path = None
            self._leaf_markers = []
            return []

    def _refresh_dots(self):
        if self._show_active:
            markers = self.find_leaf_markers()
            self._create_dot_instancer(markers)
            self._hide_icon_group_models(markers)

    # ── Select nearest marker ────────────────────────────────────────

    def select_nearest_marker(self, wx: float, wy: float, wz: float) -> dict:
        from pxr import Gf

        if not self._leaf_markers:
            return {"error": "no markers visible"}

        hit = Gf.Vec3d(wx, wy, wz)
        best_dist = float("inf")
        best_idx = 0

        for i, m in enumerate(self._leaf_markers):
            pos = Gf.Vec3d(m["x"], m["y"], m["z"])
            d = (pos - hit).GetLength()
            if d < best_dist:
                best_dist = d
                best_idx = i

        self._selected_index = best_idx
        self._selected_prim_path = self._leaf_markers[best_idx]["primPath"]
        self._update_highlight(best_idx)
        self._show_direction_line(self._selected_prim_path)

        m = self._leaf_markers[best_idx]
        print(f"[usd_edit:marker] Selected marker '{m['name']}' (dist={best_dist:.1f}) layer={m.get('layerDisplayName','?')}")
        return self._marker_response(m)

    def _marker_response(self, m: dict) -> dict:
        return {
            "primPath": m["primPath"],
            "primName": m["name"],
            "x": m["x"],
            "y": m["y"],
            "z": m["z"],
            "rotX": m.get("rotX", 0),
            "rotY": m.get("rotY", 0),
            "rotZ": m.get("rotZ", 0),
            "layerIdentifier": m.get("layerIdentifier", ""),
            "layerDisplayName": m.get("layerDisplayName", ""),
        }

    # ── Nudge marker translate ───────────────────────────────────────

    def nudge_marker_translate(self, dx: float, dy: float, dz: float, edit_original: bool = False) -> dict:
        from pxr import Usd, UsdGeom, Gf, Sdf

        if self._selected_prim_path is None or self._selected_index is None:
            return {"error": "no marker selected"}

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        prim = stage.GetPrimAtPath(self._selected_prim_path)
        if not prim or not prim.IsValid():
            return {"error": "marker prim gone"}

        xformable = UsdGeom.Xformable(prim)
        current = Gf.Vec3d(0, 0, 0)
        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                val = op.Get()
                if val is not None:
                    current = Gf.Vec3d(val)
                break

        new_pos = current + Gf.Vec3d(dx, dy, dz)

        if edit_original:
            defining_layer = self._find_defining_layer(prim)
            if not defining_layer:
                return {"error": "cannot determine defining layer"}
            target_layer = defining_layer
        else:
            target_layer = self._layer_mgr.ensure_edit_layer()
            if not target_layer:
                return {"error": "cannot create edit layer"}

        with Usd.EditContext(stage, Usd.EditTarget(target_layer)):
            attr = prim.GetAttribute("xformOp:translate")
            if attr and attr.IsValid():
                attr.Set(new_pos)
            else:
                xf = UsdGeom.Xformable(prim)
                op = xf.AddTranslateOp()
                op.Set(new_pos)

        if edit_original:
            target_layer.Save()
        else:
            self._edited_marker_paths.add(self._selected_prim_path)

        idx = self._selected_index
        if 0 <= idx < len(self._leaf_markers):
            if self._leaf_markers[idx].get("isNavShortcut"):
                wx, wy, wz = self._world_translation_for_prim(prim)
                self._leaf_markers[idx]["x"] = wx
                self._leaf_markers[idx]["y"] = wy
                self._leaf_markers[idx]["z"] = wz
            else:
                self._leaf_markers[idx]["x"] = float(new_pos[0])
                self._leaf_markers[idx]["y"] = float(new_pos[1])
                self._leaf_markers[idx]["z"] = float(new_pos[2])

        self._update_dot_positions()
        if self._selected_prim_path:
            self._show_direction_line(self._selected_prim_path)

        return self._marker_response(self._leaf_markers[idx])

    # ── Nudge marker rotate ──────────────────────────────────────────

    def nudge_marker_rotate(self, dx: float, dy: float, dz: float, edit_original: bool = False) -> dict:
        from pxr import Usd, UsdGeom, Gf

        if self._selected_prim_path is None or self._selected_index is None:
            return {"error": "no marker selected"}

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        prim = stage.GetPrimAtPath(self._selected_prim_path)
        if not prim or not prim.IsValid():
            print(f"[usd_edit:marker] nudge_rotate aborted: prim invalid at {self._selected_prim_path}")
            return {"error": "marker prim gone"}

        xformable = UsdGeom.Xformable(prim)
        current = Gf.Vec3d(0, 0, 0)
        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
                val = op.Get()
                if val is not None:
                    current = Gf.Vec3d(val)
                break

        new_rot = current + Gf.Vec3d(dx, dy, dz)

        if edit_original:
            defining_layer = self._find_defining_layer(prim)
            if not defining_layer:
                return {"error": "cannot determine defining layer"}
            target_layer = defining_layer
        else:
            target_layer = self._layer_mgr.ensure_edit_layer()
            if not target_layer:
                return {"error": "cannot create edit layer"}

        # When writing to the canonical layer, strip any stronger
        # opinions for ``xformOp:rotateXYZ`` (session + usd_edits.usda)
        # that would otherwise shadow our write — otherwise the composed
        # value never moves and every nudge appears to do nothing.
        if edit_original:
            self._strip_stronger_rotation_opinions(prim, target_layer)
            # After stripping, recompute current and new_rot from the
            # newly-effective composed value so the user's intended delta
            # applies to whatever the canonical layer actually holds
            # (which is usually different from the now-removed override).
            xformable = UsdGeom.Xformable(prim)
            current_after = Gf.Vec3d(0, 0, 0)
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
                    val = op.Get()
                    if val is not None:
                        current_after = Gf.Vec3d(val)
                    break
            new_rot = current_after + Gf.Vec3d(dx, dy, dz)

        with Usd.EditContext(stage, Usd.EditTarget(target_layer)):
            attr = prim.GetAttribute("xformOp:rotateXYZ")
            if attr and attr.IsValid():
                attr.Set(new_rot)
            else:
                xf = UsdGeom.Xformable(prim)
                op = xf.AddRotateXYZOp()
                op.Set(new_rot)

        if edit_original:
            target_layer.Save()
            edit_layer = self._layer_mgr.edit_layer
            if edit_layer:
                try:
                    edit_layer.Save()
                except Exception:
                    pass
        else:
            self._edited_marker_paths.add(self._selected_prim_path)

        idx = self._selected_index
        if 0 <= idx < len(self._leaf_markers):
            self._leaf_markers[idx]["rotX"] = float(new_rot[0])
            self._leaf_markers[idx]["rotY"] = float(new_rot[1])
            self._leaf_markers[idx]["rotZ"] = float(new_rot[2])

        if self._selected_prim_path:
            self._show_direction_line(self._selected_prim_path)

        return self._marker_response(self._leaf_markers[idx])

    # ── World transform (clipboard / external APIs) ───────────────────

    def get_selected_marker_world_transform_json(self, include_full_diagnostic: bool = False) -> dict:
        """Return ``clipboardJson`` (pretty-printed), ``clipKind``, or ``error``.

        When *include_full_diagnostic* is false (default from web), the copied
        JSON is a **flat** object: ``primPath``, ``primName``, ``location``,
        ``rotationDegWorld`` (composed scene orientation only), and a short
        ``units`` string.

        When true, the payload matches the older nested shape with ``essential``
        and ``full`` blocks (matrix, quaternion, notes).
        """
        import json
        from pxr import Usd, UsdGeom, Gf

        if self._selected_prim_path is None:
            return {
                "error": "No marker selected. Turn on Show Markers and click a marker in the scene.",
            }

        stage = _get_stage()
        if not stage:
            return {"error": "No USD stage"}

        prim = stage.GetPrimAtPath(self._selected_prim_path)
        if not prim or not prim.IsValid():
            return {"error": "Marker prim is not valid"}

        try:
            xformable = UsdGeom.Xformable(prim)
            local_to_world = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            trans = local_to_world.ExtractTranslation()

            rot_m = local_to_world.ExtractRotationMatrix()

            rot_wx = rot_wy = rot_wz = 0.0
            world_rot = _gf_rotation_from_extracted_matrix3d(rot_m)
            try:
                angles = world_rot.Decompose(
                    Gf.Vec3d(1, 0, 0),
                    Gf.Vec3d(0, 1, 0),
                    Gf.Vec3d(0, 0, 1),
                )
                rot_wx = _jf(float(angles[0]))
                rot_wy = _jf(float(angles[1]))
                rot_wz = _jf(float(angles[2]))
            except Exception:
                if (
                    self._selected_index is not None
                    and 0 <= self._selected_index < len(self._leaf_markers)
                ):
                    md = self._leaf_markers[self._selected_index]
                    rot_wx = _jf(float(md["rotX"]))
                    rot_wy = _jf(float(md["rotY"]))
                    rot_wz = _jf(float(md["rotZ"]))

            row_major = []
            for i in range(4):
                row = local_to_world[i]
                row_major.extend([
                    _jf(float(row[0])), _jf(float(row[1])),
                    _jf(float(row[2])), _jf(float(row[3])),
                ])

            q = world_rot.GetQuat()
            qi = q.GetImaginary()
            quat_payload = {
                "w": _jf(float(q.GetReal())),
                "x": _jf(float(qi[0])),
                "y": _jf(float(qi[1])),
                "z": _jf(float(qi[2])),
            }

            scale_payload = {"x": 1.0, "y": 1.0, "z": 1.0}
            try:
                xf = Gf.Transform()
                xf.SetMatrix(local_to_world)
                sc = xf.GetScale()
                scale_payload = {
                    "x": _jf(float(sc[0])),
                    "y": _jf(float(sc[1])),
                    "z": _jf(float(sc[2])),
                }
            except Exception:
                pass

            panel_rx = panel_ry = panel_rz = None
            local_panel = None
            if (
                self._selected_index is not None
                and 0 <= self._selected_index < len(self._leaf_markers)
            ):
                md = self._leaf_markers[self._selected_index]
                panel_rx = _jf(float(md["rotX"]))
                panel_ry = _jf(float(md["rotY"]))
                panel_rz = _jf(float(md["rotZ"]))
                local_panel = {
                    "translate": {
                        "x": _jf(float(md["x"])),
                        "y": _jf(float(md["y"])),
                        "z": _jf(float(md["z"])),
                    },
                    "rotateEulerDegXYZ": {
                        "x": panel_rx, "y": panel_ry, "z": panel_rz,
                    },
                }

            tx, ty, tz = _jf(float(trans[0])), _jf(float(trans[1])), _jf(float(trans[2]))
            rot_panel_block = None
            if panel_rx is not None:
                rot_panel_block = {
                    "x": panel_rx,
                    "y": panel_ry,
                    "z": panel_rz,
                }

            max_abs_delta = 0.0
            if rot_panel_block is not None:
                max_abs_delta = max(
                    abs(rot_panel_block["x"] - rot_wx),
                    abs(rot_panel_block["y"] - rot_wy),
                    abs(rot_panel_block["z"] - rot_wz),
                )

            essential_note = (
                "Use rotationDegWorld for the orientation the scene actually composes "
                "(matches full.rotationQuaternion / matrix). "
                "rotationDegPanel matches the Markers UI sliders (xformOp:rotateXYZ); "
                "for iconGroup prims it can differ when the interactions extension "
                "writes session-layer rotate (e.g. icon spin)."
            )
            if max_abs_delta > 0.5:
                essential_note += (
                    f" This prim: max |panel − world| per axis ≈ {max_abs_delta:.1f}°."
                )

            prim_path_s = str(prim.GetPath())
            prim_name_s = prim.GetName()

            nested = {
                "primPath": prim_path_s,
                "primName": prim_name_s,
                "essential": {
                    "location": {"x": tx, "y": ty, "z": tz},
                    "rotationDegWorld": {"x": rot_wx, "y": rot_wy, "z": rot_wz},
                    "rotationDegPanel": rot_panel_block,
                    "units": (
                        "Lengths: scene units (Kit is usually cm). "
                        "Angles: degrees (RotateXYZ convention for world decomposition)."
                    ),
                    "note": essential_note,
                },
                "full": {
                    "_note": (
                        "Verification bundle — compare with `essential`. "
                        "Remove `full` from emitted JSON once values are trusted."
                    ),
                    "coordinateSpace": "world",
                    "notes": (
                        "translation: ExtractTranslation(localToWorld). "
                        "rotationQuaternion: orthogonal 3×3 → Quatd (trace method) → "
                        "Gf.Rotation(Quatd); Matrix3d ctor is not bound in this Kit build. "
                        "rotationDegXYZWorld: same as essential.rotationDegWorld "
                        "(Gf.Rotation.Decompose X,Y,Z), or panel fallback if Decompose fails. "
                        "matrix4RowMajor: Gf.Matrix4d rows 0..3. "
                        "scale: Gf.Transform.SetMatrix(localToWorld).GetScale(). "
                        "localXformPanel: composed xformOp translate + rotateXYZ from "
                        "GetOrderedXformOps (Markers panel; may include session overrides)."
                    ),
                    "translation": {"x": tx, "y": ty, "z": tz},
                    "scale": scale_payload,
                    "rotationQuaternion": quat_payload,
                    "rotationDegXYZWorld": {"x": rot_wx, "y": rot_wy, "z": rot_wz},
                    "matrix4RowMajor": row_major,
                    "localXformPanel": local_panel,
                },
            }

            if include_full_diagnostic:
                body = nested
                clip_kind = "full"
            else:
                body = {
                    "primPath": prim_path_s,
                    "primName": prim_name_s,
                    "location": {"x": tx, "y": ty, "z": tz},
                    "rotationDegWorld": {"x": rot_wx, "y": rot_wy, "z": rot_wz},
                    "units": (
                        "Lengths: USD scene units (Kit is usually centimeters). "
                        "Angles: degrees (RotateXYZ Euler from the composed world matrix)."
                    ),
                }
                clip_kind = "essential"

            return {
                "clipboardJson": json.dumps(body, indent=2),
                "clipKind": clip_kind,
            }
        except Exception as exc:
            return {"error": f"World transform failed: {exc}"}

    # ── Remove marker ────────────────────────────────────────────────

    def remove_marker(self) -> dict:
        """Delete the currently selected marker from its defining layer."""
        from pxr import Sdf

        if self._selected_prim_path is None or self._selected_index is None:
            return {"error": "no marker selected"}

        stage = _get_stage()
        if not stage:
            return {"error": "no stage"}

        prim = stage.GetPrimAtPath(self._selected_prim_path)
        if not prim or not prim.IsValid():
            return {"error": "marker prim gone"}

        defining_layer = self._find_defining_layer(prim)
        if not defining_layer:
            return {"error": "cannot determine defining layer"}

        prim_path = self._selected_prim_path
        prim_name = prim.GetName()
        layer_name = self._layer_display_name(defining_layer)

        sdf_path = Sdf.Path(prim_path)
        parent_path = sdf_path.GetParentPath()
        child_name = sdf_path.name

        parent_spec = defining_layer.GetPrimAtPath(parent_path)
        if not parent_spec:
            return {"error": f"parent spec not found in {layer_name}"}

        try:
            del parent_spec.nameChildren[child_name]
        except Exception as exc:
            return {"error": f"could not delete '{child_name}' from {layer_name}: {exc}"}

        defining_layer.Save()

        # Also strip any override of the same prim from usd_edits.usda so a
        # leftover override doesn't resurrect a "ghost" spec at the same path.
        edit_layer = self._layer_mgr.edit_layer
        if edit_layer:
            edit_parent = edit_layer.GetPrimAtPath(parent_path)
            if edit_parent and child_name in edit_parent.nameChildren:
                try:
                    del edit_parent.nameChildren[child_name]
                except Exception as exc:
                    print(f"[usd_edit:marker] could not strip override from usd_edits: {exc}")

        self._edited_marker_paths.discard(prim_path)

        self._clear_direction_line()
        self._selected_index = None
        self._selected_prim_path = None

        print(f"[usd_edit:marker] Removed marker '{prim_name}' from {layer_name}")

        if self._show_active:
            self._refresh_dots()

        return {
            "primPath": prim_path,
            "primName": prim_name,
            "layerDisplayName": layer_name,
        }

    # ── Save / Reset ─────────────────────────────────────────────────

    def save_edits(self) -> int:
        if not self._edited_marker_paths:
            return 0
        self._layer_mgr.save_layer()
        count = len(self._edited_marker_paths)
        self._edited_marker_paths.clear()
        return count

    def reset_session(self) -> int:
        from pxr import Usd, Sdf

        if not self._edited_marker_paths:
            return 0

        stage = _get_stage()
        if not stage:
            return 0

        edit_layer = self._layer_mgr.edit_layer
        if not edit_layer:
            return 0

        reset = 0
        for prim_path in list(self._edited_marker_paths):
            sdf_path = Sdf.Path(prim_path)
            prim_spec = edit_layer.GetPrimAtPath(sdf_path)
            if prim_spec:
                translate_path = sdf_path.AppendProperty("xformOp:translate")
                if edit_layer.GetPropertyAtPath(translate_path):
                    edit_layer.GetPrimAtPath(sdf_path).RemoveProperty(
                        Sdf.Path("xformOp:translate")
                    )
                    reset += 1

        self._edited_marker_paths.clear()

        if self._show_active:
            self._refresh_dots()

        return reset

    # ── Exit / cleanup ───────────────────────────────────────────────

    def exit_mode(self):
        was_active = self._show_active or self.is_armed
        self._clear_direction_line()
        self._remove_dots()
        self._restore_icon_group_models()
        self._show_active = False
        self._selected_index = None
        self._selected_prim_path = None
        self._leaf_markers = []
        self.disarm()
        if was_active:
            print("[usd_edit:marker] Exited marker mode")

    # ── PointInstancer helpers ───────────────────────────────────────

    def _create_dot_instancer(self, markers: list):
        from pxr import Usd, UsdGeom, UsdShade, Vt, Gf

        stage = _get_stage()
        if not stage:
            return

        self._remove_dots()

        if not markers:
            return

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            UsdGeom.Xform.Define(stage, MARKER_DOTS_ROOT)

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

            positions = Vt.Vec3fArray([
                Gf.Vec3f(float(m["x"]), float(m["y"]), float(m["z"]))
                for m in markers
            ])
            indices = Vt.IntArray([0] * len(markers))
            if self._selected_index is not None and 0 <= self._selected_index < len(markers):
                indices[self._selected_index] = 1
            scales = Vt.Vec3fArray([Gf.Vec3f(1, 1, 1)] * len(markers))

            instancer.GetPositionsAttr().Set(positions)
            instancer.GetProtoIndicesAttr().Set(indices)
            instancer.GetScalesAttr().Set(scales)

    def _remove_dots(self):
        from pxr import Usd, UsdGeom, Vt

        stage = _get_stage()
        if not stage:
            return

        try:
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, Usd.EditTarget(session)):
                root_prim = stage.GetPrimAtPath(MARKER_DOTS_ROOT)
                if root_prim and root_prim.IsValid():
                    UsdGeom.Imageable(root_prim).MakeInvisible()

                prim = stage.GetPrimAtPath(INSTANCER_PATH)
                if prim and prim.IsValid():
                    UsdGeom.Imageable(prim).MakeInvisible()
                    inst = UsdGeom.PointInstancer(prim)
                    inst.GetPositionsAttr().Set(Vt.Vec3fArray())
                    inst.GetProtoIndicesAttr().Set(Vt.IntArray())
                    inst.GetScalesAttr().Set(Vt.Vec3fArray())
                stage.RemovePrim(MARKER_DOTS_ROOT)
        except Exception as e:
            print(f"[usd_edit:marker] dot cleanup error: {e}")

    def _update_highlight(self, selected_idx: int):
        from pxr import Usd, UsdGeom, Vt

        stage = _get_stage()
        if not stage or not self._leaf_markers:
            return

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            prim = stage.GetPrimAtPath(INSTANCER_PATH)
            if not prim or not prim.IsValid():
                return
            inst = UsdGeom.PointInstancer(prim)
            indices = [0] * len(self._leaf_markers)
            if 0 <= selected_idx < len(indices):
                indices[selected_idx] = 1
            inst.GetProtoIndicesAttr().Set(Vt.IntArray(indices))

    def _update_dot_positions(self):
        from pxr import Usd, UsdGeom, Vt, Gf

        stage = _get_stage()
        if not stage or not self._leaf_markers:
            return

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            prim = stage.GetPrimAtPath(INSTANCER_PATH)
            if not prim or not prim.IsValid():
                return
            inst = UsdGeom.PointInstancer(prim)
            positions = Vt.Vec3fArray([
                Gf.Vec3f(float(m["x"]), float(m["y"]), float(m["z"]))
                for m in self._leaf_markers
            ])
            inst.GetPositionsAttr().Set(positions)

    # ── Direction line helpers ────────────────────────────────────────

    def _show_direction_line(self, prim_path: str):
        """Draw a BasisCurves arrow from the marker in its forward direction."""
        import math
        from pxr import Usd, UsdGeom, Gf, Vt

        stage = _get_stage()
        if not stage:
            return

        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return

        xformable = UsdGeom.Xformable(prim)
        translate = Gf.Vec3d(0, 0, 0)
        rotate = Gf.Vec3d(0, 0, 0)

        for op in xformable.GetOrderedXformOps():
            op_type = op.GetOpType()
            val = op.Get()
            if val is None:
                continue
            if op_type == UsdGeom.XformOp.TypeTranslate:
                translate = Gf.Vec3d(val)
            elif op_type == UsdGeom.XformOp.TypeRotateXYZ:
                rotate = Gf.Vec3d(val)

        rx = math.radians(rotate[0])
        ry = math.radians(rotate[1])
        rz = math.radians(rotate[2])

        # USD default forward is -Z; apply rotateXYZ (X then Y then Z)
        # Forward vector after rotation:
        fwd_x = -math.sin(ry) * math.cos(rx)
        fwd_y = math.sin(rx)
        fwd_z = -math.cos(ry) * math.cos(rx)

        length = DIRECTION_LINE_LENGTH
        start = Gf.Vec3f(float(translate[0]), float(translate[1]), float(translate[2]))
        end = Gf.Vec3f(
            float(translate[0] + fwd_x * length),
            float(translate[1] + fwd_y * length),
            float(translate[2] + fwd_z * length),
        )

        # Arrowhead: two short segments angled inward
        head_len = length * 0.18
        head_spread = head_len * 0.45
        fwd_norm = math.sqrt(fwd_x ** 2 + fwd_z ** 2) or 1.0
        perp_x = -fwd_z / fwd_norm
        perp_z = fwd_x / fwd_norm
        back_x = -fwd_x
        back_z = -fwd_z
        back_norm = math.sqrt(back_x ** 2 + back_z ** 2) or 1.0
        back_x /= back_norm
        back_z /= back_norm

        arrow_l = Gf.Vec3f(
            float(end[0] + back_x * head_len + perp_x * head_spread),
            float(end[1]),
            float(end[2] + back_z * head_len + perp_z * head_spread),
        )
        arrow_r = Gf.Vec3f(
            float(end[0] + back_x * head_len - perp_x * head_spread),
            float(end[1]),
            float(end[2] + back_z * head_len - perp_z * head_spread),
        )

        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, Usd.EditTarget(session)):
            curves = UsdGeom.BasisCurves.Define(stage, DIRECTION_LINE_PATH)
            curves.CreateTypeAttr("linear")
            # Three curves: main shaft + two arrowhead wings
            curves.CreateCurveVertexCountsAttr([2, 2, 2])
            curves.CreatePointsAttr([start, end, end, arrow_l, end, arrow_r])
            curves.CreateWidthsAttr([DIRECTION_LINE_WIDTH] * 6)
            curves.GetDisplayColorAttr().Set([Gf.Vec3f(*DIRECTION_LINE_COLOR)])

    def _clear_direction_line(self):
        from pxr import Usd, UsdGeom

        stage = _get_stage()
        if not stage:
            return

        prim = stage.GetPrimAtPath(DIRECTION_LINE_PATH)
        if prim and prim.IsValid():
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, Usd.EditTarget(session)):
                UsdGeom.Imageable(prim).MakeInvisible()
                stage.RemovePrim(DIRECTION_LINE_PATH)
