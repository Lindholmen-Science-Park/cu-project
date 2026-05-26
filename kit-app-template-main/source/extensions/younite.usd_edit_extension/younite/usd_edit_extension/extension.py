import omni.ext


class UsdEditExtension(omni.ext.IExt):
    """Lightweight USD editing for streaming dev mode:
    vertex nudging, prim transforms (move/rotate), persistent sublayer."""

    def on_startup(self, ext_id: str):
        print("[usd_edit] on_startup called")
        self._ext_id = ext_id
        self._subs = []
        self._deferred_init_sub = None

        from .edit_layer_manager import EditLayerManager
        from .vertex_edit_service import VertexEditService
        from .prim_transform_service import PrimTransformService
        from .marker_service import MarkerService

        self._layer_mgr = EditLayerManager()
        self._vertex_svc = VertexEditService(self._layer_mgr)
        self._transform_svc = PrimTransformService(self._layer_mgr)
        self._marker_svc = MarkerService(self._layer_mgr)

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
                dispatch_to_events2,
                register_outbound_events,
            )

            register_outbound_events([
                "usdEditStateUpdate",
                "usdEditVertexSelected",
                "usdEditTransformUpdate",
                "usdEditSaveStatus",
                "usdEditSublayerList",
                "usdEditMarkerCreated",
                "usdEditMarkerList",
                "usdEditMarkerSelected",
                "usdEditMarkerRemoved",
                "usdEditMarkerWorldTransform",
            ])

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.usd_edit_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            # ── Pick result (dispatched by intent) ───────────────

            def _on_pick_result(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                intent = str(payload.get("intent") or "")

                hit = payload.get("hit")
                if not hit or not isinstance(hit, dict) or not hit.get("world"):
                    return

                w = hit["world"]
                wx = float(w.get("x", 0))
                wy = float(w.get("y", 0))
                wz = float(w.get("z", 0))

                if intent == "vertexEdit":
                    self._handle_vertex_pick(hit, wx, wy, wz, dispatch_to_events2)
                elif intent == "usdEditTransform":
                    self._handle_transform_pick(hit, dispatch_to_events2)
                elif intent == "usdEditMarker":
                    self._handle_marker_pick(wx, wy, wz, dispatch_to_events2)

            # ── Vertex edit messages ─────────────────────────────

            def _on_move_vertex(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                index = payload.get("vertexIndex")
                if index is None:
                    return
                result = self._vertex_svc.nudge_vertex(
                    int(index),
                    float(payload.get("dx", 0)),
                    float(payload.get("dy", 0)),
                    float(payload.get("dz", 0)),
                )
                if "error" not in result:
                    dispatch_to_events2("usdEditVertexSelected", result)

            def _on_set_vertex(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                index = payload.get("vertexIndex")
                if index is None:
                    return
                result = self._vertex_svc.move_vertex(
                    int(index),
                    float(payload.get("x", 0)),
                    float(payload.get("y", 0)),
                    float(payload.get("z", 0)),
                )
                if "error" not in result:
                    dispatch_to_events2("usdEditVertexSelected", result)

            def _on_drag_vertex(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                result = self._vertex_svc.drag_vertex(
                    float(payload.get("dx", 0)),
                    float(payload.get("dy", 0)),
                )
                if "error" not in result:
                    dispatch_to_events2("usdEditVertexSelected", result)

            # ── Measure messages ─────────────────────────────────

            def _on_highlight_vertices(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                indices = payload.get("indices", [])
                if isinstance(indices, list):
                    self._vertex_svc.highlight_multiple([int(i) for i in indices])

            def _on_draw_measure_line(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._vertex_svc.draw_measure_line(
                    float(payload.get("x1", 0)), float(payload.get("y1", 0)), float(payload.get("z1", 0)),
                    float(payload.get("x2", 0)), float(payload.get("y2", 0)), float(payload.get("z2", 0)),
                )

            def _on_clear_measure_line(evt):
                self._vertex_svc.clear_measure_line()
                self._vertex_svc.highlight_multiple([])

            # ── Transform messages ───────────────────────────────

            def _on_nudge_translate(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                result = self._transform_svc.nudge_translate(
                    float(payload.get("dx", 0)),
                    float(payload.get("dy", 0)),
                    float(payload.get("dz", 0)),
                )
                if "error" not in result:
                    dispatch_to_events2("usdEditTransformUpdate", result)

            def _on_nudge_rotate(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                result = self._transform_svc.nudge_rotate(
                    float(payload.get("dx", 0)),
                    float(payload.get("dy", 0)),
                    float(payload.get("dz", 0)),
                )
                if "error" not in result:
                    dispatch_to_events2("usdEditTransformUpdate", result)

            # ── Marker messages ────────────────────────────────────

            def _on_request_sublayers(evt):
                sublayers = self._marker_svc.list_active_sublayers()
                dispatch_to_events2("usdEditSublayerList", {"sublayers": sublayers})

            def _on_arm_marker_placement(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                sublayer = str(payload.get("sublayerIdentifier") or "")
                name = str(payload.get("markerName") or "")
                if sublayer and name:
                    self._marker_svc.arm_placement(sublayer, name)

            def _on_show_markers(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                visible = payload.get("visible", False)
                markers = self._marker_svc.show_markers(bool(visible))
                dispatch_to_events2("usdEditMarkerList", {"markers": markers, "visible": bool(visible)})

            def _on_nudge_marker_translate(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                result = self._marker_svc.nudge_marker_translate(
                    float(payload.get("dx", 0)),
                    float(payload.get("dy", 0)),
                    float(payload.get("dz", 0)),
                    edit_original=bool(payload.get("editOriginal", False)),
                )
                if "error" not in result:
                    dispatch_to_events2("usdEditMarkerSelected", result)

            def _on_nudge_marker_rotate(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                result = self._marker_svc.nudge_marker_rotate(
                    float(payload.get("dx", 0)),
                    float(payload.get("dy", 0)),
                    float(payload.get("dz", 0)),
                    edit_original=bool(payload.get("editOriginal", False)),
                )
                if "error" not in result:
                    dispatch_to_events2("usdEditMarkerSelected", result)

            def _on_remove_marker(evt):
                result = self._marker_svc.remove_marker()
                if "error" not in result:
                    dispatch_to_events2("usdEditMarkerRemoved", result)
                else:
                    print(f"[usd_edit:marker] remove error: {result['error']}")

            def _on_copy_marker_world_transform(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                include_full = bool(payload.get("includeFullDiagnostic", False))
                result = self._marker_svc.get_selected_marker_world_transform_json(
                    include_full_diagnostic=include_full,
                )
                dispatch_to_events2("usdEditMarkerWorldTransform", result)

            def _on_exit_marker_mode(evt):
                """Clean up marker dots only (tab switch), no phase dispatch."""
                self._marker_svc.exit_mode()

            # ── Mode exit ────────────────────────────────────────

            def _on_exit_edit_mode(evt):
                self._vertex_svc.exit_edit_mode()
                self._transform_svc.exit_transform_mode()
                self._marker_svc.exit_mode()
                dispatch_to_events2("usdEditStateUpdate", {"phase": "idle"})

            def _on_exit_vertex_dots(evt):
                """Clean up vertex dots only (tab switch), no phase dispatch."""
                self._vertex_svc.exit_edit_mode()

            # ── Save / Reset (combined across all services) ──────

            def _on_save(evt):
                v = self._vertex_svc.save_edits()
                t = self._transform_svc.save_edits()
                m = self._marker_svc.save_edits()
                total = v + t + m
                self._layer_mgr.save_layer()
                msg = f"Saved {total} edit(s)" if total else "No unsaved edits"
                print(f"[usd_edit] {msg}")
                dispatch_to_events2("usdEditSaveStatus", {"status": "saved" if total else "nothing", "message": msg})

            def _on_reset_session(evt):
                v = self._vertex_svc.reset_session()
                t = self._transform_svc.reset_session()
                m = self._marker_svc.reset_session()
                total = v + t + m
                msg = f"Reset {total} session edit(s)" if total else "No session edits to reset"
                print(f"[usd_edit] {msg}")
                dispatch_to_events2("usdEditSaveStatus", {"status": "reset" if total else "nothing", "message": msg})

            def _on_hard_reset(evt):
                self._vertex_svc.reset_session()
                self._transform_svc.reset_session()
                self._marker_svc.reset_session()
                self._layer_mgr.clear_layer()
                dispatch_to_events2("usdEditSaveStatus", {"status": "hard_reset", "message": "All edits cleared"})

            _observe("younite.pick.result", _on_pick_result)
            _observe("usdEdit.moveVertex", _on_move_vertex)
            _observe("usdEdit.setVertex", _on_set_vertex)
            _observe("usdEdit.dragVertex", _on_drag_vertex)
            _observe("usdEdit.highlightVertices", _on_highlight_vertices)
            _observe("usdEdit.drawMeasureLine", _on_draw_measure_line)
            _observe("usdEdit.clearMeasureLine", _on_clear_measure_line)
            _observe("usdEdit.nudgeTranslate", _on_nudge_translate)
            _observe("usdEdit.nudgeRotate", _on_nudge_rotate)
            _observe("usdEdit.exitEditMode", _on_exit_edit_mode)
            _observe("usdEdit.exitVertexDots", _on_exit_vertex_dots)
            _observe("usdEdit.requestSublayers", _on_request_sublayers)
            _observe("usdEdit.armMarkerPlacement", _on_arm_marker_placement)
            _observe("usdEdit.showMarkers", _on_show_markers)
            _observe("usdEdit.nudgeMarkerTranslate", _on_nudge_marker_translate)
            _observe("usdEdit.nudgeMarkerRotate", _on_nudge_marker_rotate)
            _observe("usdEdit.removeMarker", _on_remove_marker)
            _observe("usdEdit.copyMarkerWorldTransform", _on_copy_marker_world_transform)
            _observe("usdEdit.exitMarkerMode", _on_exit_marker_mode)
            _observe("usdEdit.save", _on_save)
            _observe("usdEdit.resetSession", _on_reset_session)
            _observe("usdEdit.hardReset", _on_hard_reset)

            # Deferred auto-load of existing edit layer
            def _deferred_init(evt):
                from .edit_layer_manager import _get_stage
                stage = _get_stage()
                if not stage or not stage.GetRootLayer().realPath:
                    return
                self._layer_mgr.load_existing_edit_layer()
                self._deferred_init_sub = None

            self._deferred_init_sub = ed.observe_event(
                observer_name="younite.usd_edit_extension/deferred_init",
                event_name=kit_app.GLOBAL_EVENT_UPDATE,
                on_event=_deferred_init,
                order=1000,
            )

            print("[usd_edit] extension loaded")
        except Exception as e:
            print(f"[usd_edit] startup failed: {e}")
            import traceback
            traceback.print_exc()

    # ── Pick dispatch helpers ────────────────────────────────────────

    def _handle_vertex_pick(self, hit, wx, wy, wz, dispatch):
        prim_path = hit.get("primPath") or hit.get("bodyPrimPath") or ""

        if self._vertex_svc.active_mesh_path is None:
            if not prim_path:
                return
            mesh_path = self._find_mesh_ancestor(str(prim_path))
            if not mesh_path:
                print(f"[usd_edit:vertex] no mesh found at or above {prim_path}")
                return
            result = self._vertex_svc.enter_mesh_edit(mesh_path)
            if "error" in result:
                dispatch("usdEditStateUpdate", {"phase": "error", "error": result["error"]})
                return
            dispatch("usdEditStateUpdate", {
                "phase": "meshSelected",
                "meshPath": result["meshPath"],
                "vertexCount": result["vertexCount"],
            })
        else:
            result = self._vertex_svc.select_closest_vertex(wx, wy, wz)
            if "error" not in result:
                dispatch("usdEditVertexSelected", result)

    def _handle_transform_pick(self, hit, dispatch):
        prim_path = hit.get("primPath") or hit.get("bodyPrimPath") or ""
        if not prim_path:
            return

        # Walk up to find a meaningful Xform / scope ancestor (skip sub-meshes)
        xform_path = self._find_xformable_ancestor(str(prim_path))
        if not xform_path:
            print(f"[usd_edit:transform] no transformable prim at {prim_path}")
            return

        result = self._transform_svc.select_prim(xform_path)
        if "error" in result:
            dispatch("usdEditStateUpdate", {"phase": "error", "error": result["error"]})
            return
        dispatch("usdEditStateUpdate", {"phase": "primSelected"})
        dispatch("usdEditTransformUpdate", result)

    def _handle_marker_pick(self, wx, wy, wz, dispatch):
        if self._marker_svc.is_armed:
            result = self._marker_svc.create_marker_at(wx, wy, wz)
            if "error" in result:
                dispatch("usdEditStateUpdate", {"phase": "error", "error": result["error"]})
                return
            dispatch("usdEditMarkerCreated", result)
            dispatch("usdEditStateUpdate", {"phase": "markerCreated"})
        elif self._marker_svc._show_active:
            result = self._marker_svc.select_nearest_marker(wx, wy, wz)
            if "error" not in result:
                dispatch("usdEditMarkerSelected", result)
                dispatch("usdEditStateUpdate", {"phase": "markerSelected"})

    # ── Prim ancestry helpers ────────────────────────────────────────

    def _find_mesh_ancestor(self, prim_path: str):
        try:
            import omni.usd
            from pxr import UsdGeom, Sdf
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return None
            path = Sdf.Path(prim_path)
            while path != Sdf.Path.absoluteRootPath:
                prim = stage.GetPrimAtPath(path)
                if prim and prim.IsValid() and prim.IsA(UsdGeom.Mesh):
                    return str(path)
                path = path.GetParentPath()
        except Exception as e:
            print(f"[usd_edit] mesh ancestor search error: {e}")
        return None

    def _find_xformable_ancestor(self, prim_path: str):
        """Walk up to find the nearest Xformable prim (skip /World root)."""
        try:
            import omni.usd
            from pxr import UsdGeom, Sdf
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return None
            path = Sdf.Path(prim_path)
            while path != Sdf.Path.absoluteRootPath:
                if str(path) == "/World":
                    break
                prim = stage.GetPrimAtPath(path)
                if prim and prim.IsValid() and prim.IsA(UsdGeom.Xformable):
                    return str(path)
                path = path.GetParentPath()
        except Exception as e:
            print(f"[usd_edit] xformable ancestor search error: {e}")
        return None

    def on_shutdown(self):
        self._deferred_init_sub = None
        if getattr(self, "_vertex_svc", None):
            self._vertex_svc.exit_edit_mode()
        if getattr(self, "_transform_svc", None):
            self._transform_svc.exit_transform_mode()
        if getattr(self, "_marker_svc", None):
            self._marker_svc.exit_mode()
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._vertex_svc = None
        self._transform_svc = None
        self._marker_svc = None
        self._layer_mgr = None
