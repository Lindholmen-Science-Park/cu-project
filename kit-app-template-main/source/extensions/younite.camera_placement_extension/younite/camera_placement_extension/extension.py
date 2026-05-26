import math

import omni.ext

_PLACED_CAMERAS_ROOT = "/World/PlacedCameras"
_HEIGHT_OFFSET = 0.0


class CameraPlacementExtension(omni.ext.IExt):
    """Place, manage, and rotate cameras at world positions via pick results."""

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._enabled = False
        self._placed_cameras = []  # [{ "id": str, "label": str, "primPath": str }]
        self._camera_counter = 0
        self._camera_orientations = {}  # { cam_id: {"yaw": float, "pitch": float} }
        self._hidden_visual = None  # prim path of currently hidden visual cube

        try:
            import carb.eventdispatcher
            import carb.events
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
                register_outbound_events,
            )

            register_outbound_events(["placedCamerasSync"])

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.camera_placement_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            _observe("cameraPlacementToggle", self._on_toggle)
            _observe("younite.pick.result", self._on_pick_result)
            _observe("placedCameraRotate", self._on_rotate)
            _observe("placedCameraLens", self._on_lens)
            _observe("placedCameraRemove", self._on_remove)
            _observe("placedCamerasListRequest", self._on_list_request)
            _observe("fixedCameraStatus", self._on_fixed_camera_status)
        except Exception as e:
            print(f"[camera_placement] subscribe failed: {e}")

    def on_shutdown(self):
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._placed_cameras = []

    # ── Event handlers ──────────────────────────────────────────────

    def _on_toggle(self, evt):
        from younite.messaging_core_extension.message_utils import normalize_event_payload

        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        self._enabled = bool(payload.get("enabled", False))
        print(f"[camera_placement] placement {'enabled' if self._enabled else 'disabled'}")

    def _on_pick_result(self, evt):
        from younite.messaging_core_extension.message_utils import normalize_event_payload

        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        if not self._enabled:
            return
        if str(payload.get("intent") or "") != "cameraPlacement":
            return
        hit = payload.get("hit")
        if not hit or not isinstance(hit, dict) or not hit.get("world"):
            return
        w = hit["world"]
        try:
            pos = (float(w["x"]), float(w["y"]) + _HEIGHT_OFFSET, float(w["z"]))
        except (KeyError, TypeError, ValueError):
            return

        camera_yaw = float(payload.get("cameraYaw") or 0.0)
        camera_pitch = float(payload.get("cameraPitch") or -15.0)

        self._create_camera(pos, camera_yaw, camera_pitch)

    def _on_rotate(self, evt):
        from younite.messaging_core_extension.message_utils import normalize_event_payload

        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        camera_id = str(payload.get("cameraId") or "").strip()
        if not camera_id:
            return

        entry = next((c for c in self._placed_cameras if c["id"] == camera_id), None)
        if not entry:
            return

        delta_yaw = float(payload.get("deltaYaw") or 0.0)
        delta_pitch = float(payload.get("deltaPitch") or 0.0)
        if delta_yaw == 0.0 and delta_pitch == 0.0:
            return

        ori = self._camera_orientations.get(camera_id, {"yaw": 0.0, "pitch": 0.0})
        ori["yaw"] = ori["yaw"] + delta_yaw
        ori["pitch"] = max(-89.0, min(89.0, ori["pitch"] + delta_pitch))
        self._camera_orientations[camera_id] = ori

        self._write_rotation(entry["primPath"], ori["yaw"], ori["pitch"])

    def _on_lens(self, evt):
        from younite.messaging_core_extension.message_utils import normalize_event_payload

        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        camera_id = str(payload.get("cameraId") or "").strip()
        if not camera_id:
            return

        entry = next((c for c in self._placed_cameras if c["id"] == camera_id), None)
        if not entry:
            return

        focal_length = payload.get("focalLength")
        if focal_length is not None:
            self._set_focal_length(entry["primPath"], float(focal_length))

    def _on_remove(self, evt):
        from younite.messaging_core_extension.message_utils import normalize_event_payload

        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        camera_id = str(payload.get("cameraId") or "").strip()
        if not camera_id:
            return

        entry = next((c for c in self._placed_cameras if c["id"] == camera_id), None)
        if not entry:
            return

        self._remove_camera(entry)

    def _on_fixed_camera_status(self, evt):
        from younite.messaging_core_extension.message_utils import normalize_event_payload

        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        active = bool(payload.get("active", False))
        cam_path = str(payload.get("cameraPrimPath") or "")

        self._toggle_visual_for_active_camera(cam_path if active else "")

    def _on_list_request(self, _evt):
        self._sync_camera_list()

    # ── Camera CRUD ─────────────────────────────────────────────────

    def _get_player_position(self, stage):
        """Read the player character's current world position."""
        from pxr import UsdGeom, Gf

        player_prim = stage.GetPrimAtPath("/World/PlayerCharacter")
        if not player_prim or not player_prim.IsValid():
            return None
        xformable = UsdGeom.Xformable(player_prim)
        world_mtx = xformable.ComputeLocalToWorldTransform(0)
        t = world_mtx.ExtractTranslation()
        return (t[0], t[1], t[2])

    def _compute_yaw_to_target(self, from_pos, to_pos):
        """Compute yaw in degrees so a camera at from_pos faces toward to_pos (horizontal only)."""
        dx = to_pos[0] - from_pos[0]
        dz = to_pos[2] - from_pos[2]
        return math.degrees(math.atan2(-dx, -dz))

    def _build_fps_matrix(self, position, yaw_deg, pitch_deg):
        """Build a GfMatrix4d for an FPS camera: yaw around world Y, pitch around local X."""
        from pxr import Gf

        y = math.radians(yaw_deg)
        p = math.radians(pitch_deg)
        cy, sy = math.cos(y), math.sin(y)
        cp, sp = math.cos(p), math.sin(p)

        m = Gf.Matrix4d(1)
        m.SetRow(0, Gf.Vec4d(cy,      0,   -sy,         0))
        m.SetRow(1, Gf.Vec4d(sp * sy,  cp,   sp * cy,    0))
        m.SetRow(2, Gf.Vec4d(cp * sy, -sp,   cp * cy,    0))
        m.SetRow(3, Gf.Vec4d(position[0], position[1], position[2], 1))
        return m

    def _create_camera(self, position, yaw, pitch):
        try:
            import omni.usd
            from pxr import Usd, UsdGeom, Gf, Sdf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                print("[camera_placement] no stage available")
                return

            player_pos = self._get_player_position(stage)
            if player_pos:
                yaw = self._compute_yaw_to_target(position, player_pos)
                pitch = 0.0

            root_prim = stage.GetPrimAtPath(_PLACED_CAMERAS_ROOT)
            session = stage.GetSessionLayer()
            edit_ctx = Usd.EditContext(stage, Usd.EditTarget(session))

            with edit_ctx:
                if not root_prim or not root_prim.IsValid():
                    UsdGeom.Scope.Define(stage, _PLACED_CAMERAS_ROOT)

                self._camera_counter += 1
                cam_id = f"placed_cam_{self._camera_counter}"
                cam_path = f"{_PLACED_CAMERAS_ROOT}/{cam_id}"
                cam = UsdGeom.Camera.Define(stage, cam_path)
                prim = cam.GetPrim()

                prim.GetAttribute("clippingRange").Set(Gf.Vec2f(1.0, 10000000.0))
                prim.GetAttribute("focalLength").Set(12.0)
                prim.GetAttribute("focusDistance").Set(400.0)

                xform = UsdGeom.Xformable(prim)
                xform.ClearXformOpOrder()
                xform.AddTransformOp().Set(self._build_fps_matrix(position, yaw, pitch))

                self._create_camera_visual(stage, cam_path, position)

            self._camera_orientations[cam_id] = {"yaw": yaw, "pitch": pitch}

            label = f"Camera {self._camera_counter}"
            self._placed_cameras.append({
                "id": cam_id,
                "label": label,
                "primPath": cam_path,
            })
            self._toggle_visual_for_active_camera(cam_path)

            print(f"[camera_placement] created {cam_id} at {position} yaw={yaw:.1f} pitch={pitch:.1f}")
            self._sync_camera_list()
            self._switch_to_camera(cam_path, cam_id)

        except Exception as e:
            print(f"[camera_placement] create failed: {e}")

    def _create_camera_visual(self, stage, cam_path, position):
        """Create a small colored cube at the camera location as a visual marker."""
        from pxr import UsdGeom, Gf, Vt

        vis_path = f"{cam_path}_visual"
        cube = UsdGeom.Cube.Define(stage, vis_path)
        cube_prim = cube.GetPrim()

        cube.GetSizeAttr().Set(20.0)
        cube.GetExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(-10), Gf.Vec3f(10)]))

        cube_xform = UsdGeom.Xformable(cube_prim)
        cube_xform.ClearXformOpOrder()
        cube_xform.AddTranslateOp().Set(Gf.Vec3d(*position))

        cube.GetDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0.2, 0.5, 1.0)]))

    _NAVMESH_ROOTS = ["/World/ShortestPathCurve", "/World/NavmeshRoutes", "/World/NavmeshCameraAreas"]

    def _toggle_visual_for_active_camera(self, active_cam_path):
        """Hide the visual cube and NavMesh debug prims when viewing a placed camera; restore on exit."""
        try:
            import omni.usd
            from pxr import Usd, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            session = stage.GetSessionLayer()
            edit_ctx = Usd.EditContext(stage, Usd.EditTarget(session))
            is_placed = active_cam_path.startswith(_PLACED_CAMERAS_ROOT + "/")

            with edit_ctx:
                if self._hidden_visual:
                    vis_prim = stage.GetPrimAtPath(self._hidden_visual)
                    if vis_prim and vis_prim.IsValid():
                        UsdGeom.Imageable(vis_prim).MakeVisible()
                    self._hidden_visual = None

                if is_placed:
                    vis_path = f"{active_cam_path}_visual"
                    vis_prim = stage.GetPrimAtPath(vis_path)
                    if vis_prim and vis_prim.IsValid():
                        UsdGeom.Imageable(vis_prim).MakeInvisible()
                        self._hidden_visual = vis_path

            self._set_navmesh_debug_visible(stage, not is_placed)

        except Exception as e:
            print(f"[camera_placement] visual toggle failed: {e}")

    def _set_navmesh_debug_visible(self, stage, visible):
        """Hide or show NavMesh debug visualizations (route spheres, area meshes)."""
        try:
            from pxr import Usd, UsdGeom

            session = stage.GetSessionLayer()
            edit_ctx = Usd.EditContext(stage, Usd.EditTarget(session))

            with edit_ctx:
                for root_path in self._NAVMESH_ROOTS:
                    prim = stage.GetPrimAtPath(root_path)
                    if prim and prim.IsValid():
                        img = UsdGeom.Imageable(prim)
                        if visible:
                            img.MakeVisible()
                        else:
                            img.MakeInvisible()
        except Exception as e:
            print(f"[camera_placement] navmesh visibility toggle failed: {e}")

    def _remove_camera(self, entry):
        try:
            import omni.usd
            from pxr import Usd, Sdf
            from omni.kit.viewport.utility import get_active_viewport

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            viewport = get_active_viewport()
            active_cam = str(viewport.get_active_camera()) if viewport else ""
            is_viewing_this = active_cam == entry["primPath"]

            session = stage.GetSessionLayer()
            edit_ctx = Usd.EditContext(stage, Usd.EditTarget(session))
            with edit_ctx:
                stage.RemovePrim(entry["primPath"])
                visual_path = f"{entry['primPath']}_visual"
                if stage.GetPrimAtPath(visual_path):
                    stage.RemovePrim(visual_path)

            if self._hidden_visual == visual_path:
                self._hidden_visual = None

            self._placed_cameras = [c for c in self._placed_cameras if c["id"] != entry["id"]]
            self._camera_orientations.pop(entry["id"], None)
            print(f"[camera_placement] removed {entry['id']}")
            self._sync_camera_list()

            if is_viewing_this:
                self._exit_fixed_camera()

        except Exception as e:
            print(f"[camera_placement] remove failed: {e}")

    def _write_rotation(self, prim_path, yaw, pitch):
        """Rewrite the full transform matrix preserving position, updating rotation."""
        try:
            import omni.usd
            from pxr import Usd, UsdGeom, Gf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                return

            session = stage.GetSessionLayer()
            edit_ctx = Usd.EditContext(stage, Usd.EditTarget(session))

            xform = UsdGeom.Xformable(prim)
            transform_op = None
            for op in xform.GetOrderedXformOps():
                if op.GetOpName() == "xformOp:transform":
                    transform_op = op
                    break

            if not transform_op:
                return

            current = transform_op.Get()
            pos = (current[3][0], current[3][1], current[3][2])

            with edit_ctx:
                transform_op.Set(self._build_fps_matrix(pos, yaw, pitch))

        except Exception as e:
            print(f"[camera_placement] rotation failed: {e}")

    def _switch_to_camera(self, cam_path, cam_id):
        """Switch the viewport to a placed camera via the existing fixedCameraSwitchRequest path."""
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2
            dispatch_to_events2("fixedCameraSwitchRequest", {"cameraPrimPath": cam_path})
        except Exception as e:
            print(f"[camera_placement] auto-switch failed: {e}")

    def _exit_fixed_camera(self):
        """Exit fixed camera mode back to first person via the existing service."""
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2
            dispatch_to_events2("fixedCameraExitRequest", {})
        except Exception as e:
            print(f"[camera_placement] exit camera failed: {e}")

    def _set_focal_length(self, prim_path, focal_length):
        try:
            import omni.usd
            from pxr import Usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                return

            focal_length = max(4.0, min(200.0, focal_length))

            session = stage.GetSessionLayer()
            edit_ctx = Usd.EditContext(stage, Usd.EditTarget(session))
            with edit_ctx:
                prim.GetAttribute("focalLength").Set(float(focal_length))

        except Exception as e:
            print(f"[camera_placement] lens change failed: {e}")

    # ── Sync to web ─────────────────────────────────────────────────

    def _sync_camera_list(self):
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            cameras = [{"id": c["id"], "label": c["label"], "primPath": c["primPath"]} for c in self._placed_cameras]
            dispatch_to_events2("placedCamerasSync", {"cameras": cameras})
        except Exception as e:
            print(f"[camera_placement] sync failed: {e}")
