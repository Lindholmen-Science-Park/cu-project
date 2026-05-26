import omni.ext


class ViewportSafetyExtension(omni.ext.IExt):
    """
    Port of the old monolith's:
      - _disable_manipulators
      - _setup_tool_blocker
      - _setup_selection_clearer

    Purpose: prevent highlight/selection/manipulators in a viewer/streaming app.
    Diagnostics: print() only.
    """

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        try:
            import carb.settings as carb_settings
            self._settings = carb_settings.get_settings()
        except Exception:
            self._settings = None

        self._tool_blocker_subscriptions = None
        self._selection_clearer_subscription = None
        self._selection_disable_guard = None

        self._disable_manipulators()

    def _disable_manipulators(self):
        """
        Disable manipulator extensions and prim selection.
        Ensures prims cannot be selected or manipulated via the viewport.
        """
        try:
            from omni.kit.viewport.utility import get_active_viewport, disable_selection
            import omni.usd
            import carb.settings as carb_settings

            settings = self._settings if self._settings else carb_settings.get_settings()

            # Disable transform gizmo via settings
            try:
                settings.set("/app/viewport/defaults/transform/gizmoVisible", False)
                settings.set("/app/viewport/defaults/transform/gizmoEnabled", False)
                settings.set("/persistent/app/viewport/defaults/transform/gizmoVisible", False)
                settings.set("/persistent/app/viewport/defaults/transform/gizmoEnabled", False)
                # Enforce picking mode off at runtime (not just defaults)
                settings.set("/app/viewport/pickingMode", "none")
                settings.set("/persistent/app/viewport/pickingMode", "none")
                # Also disable via transform manipulator extension settings
                settings.set("/exts/omni.kit.manipulator.transform/enabled", False)
                settings.set("/exts/omni.kit.viewport.manipulator.transform/enabled", False)
                settings.set("/exts/omni.kit.manipulator.selector/enabled", False)
                print("[viewport_safety] disabled transform gizmo via settings")
            except Exception as e:
                print(f"[viewport_safety] could not disable gizmo via settings: {e}")

            # Disable selection rect + click selection via viewport utility API.
            # The returned guard object MUST be stored — it re-enables selection
            # when garbage-collected.
            self._apply_disable_selection(get_active_viewport, disable_selection)

            # Clear any existing selection and ensure nothing is pickable
            try:
                ctx = omni.usd.get_context()
                if ctx:
                    selection = ctx.get_selection()
                    if selection:
                        selection.clear_selected_prim_paths()
                    ctx.set_pickable("/", False)
            except Exception:
                pass

            # Force tools off so transform gizmo cannot be activated
            self._setup_tool_blocker()

            # Immediately clear any selection changes
            self._setup_selection_clearer()

            # Disable scroll, RMB, and MMB camera controls so point-and-click
            # (left click / touch drag) is the only look; avoids camera rotation conflicts.
            self._disable_scroll_and_mouse_camera_gestures()

        except Exception as e:
            print(f"[viewport_safety] error disabling manipulators: {e}")

    def _disable_scroll_and_mouse_camera_gestures(self):
        """
        Disable viewport scroll (zoom), right-mouse (look/orbit), and middle-mouse (pan)
        so only point-and-click / touch look drive the camera. Removes gesture keys
        entirely (empty string causes "Unparsable binding" errors).
        """
        try:
            import carb.settings as carb_settings

            settings = self._settings if self._settings else carb_settings.get_settings()
            if not settings:
                return

            bindings_path = "/exts/omni.kit.viewport.window/bindings/camera"
            current = settings.get(bindings_path)
            if current is None:
                current = {}

            custom = dict(current)

            # Remove scroll zoom (setting to "" causes "Unparsable binding").
            custom.pop("ZoomScrollGesture", None)

            # Remove RMB gestures so right mouse does nothing.
            for key in ("LookGesture", "ZoomGesture", "FlightSpeedGesture", "FlightMode"):
                val = custom.get(key)
                if val and "RightButton" in str(val):
                    custom.pop(key, None)

            # Remove MMB (middle-mouse) so pan/look with middle button is disabled.
            if custom.get("PanGesture") and "MiddleButton" in str(custom.get("PanGesture", "")):
                custom.pop("PanGesture", None)
            for key in ("LookGesture", "TumbleGesture"):
                val = custom.get(key)
                if val and "MiddleButton" in str(val):
                    custom.pop(key, None)

            settings.set(bindings_path, custom)
            settings.set("/persistent" + bindings_path, custom)
            print("[viewport_safety] disabled scroll, RMB, and MMB camera gestures (bindings updated)")
        except Exception as e:
            print(f"[viewport_safety] could not disable camera gestures: {e}")

    def _apply_disable_selection(self, get_active_viewport, disable_selection):
        """
        Call disable_selection and keep the guard alive.  If the viewport
        isn't available yet (common at startup), retry after a short delay.
        """
        viewport = get_active_viewport()
        if viewport:
            try:
                self._selection_disable_guard = disable_selection(viewport)
                print("[viewport_safety] disabled viewport selection (guard stored)")
            except Exception as e:
                print(f"[viewport_safety] disable_selection failed: {e}")
            return

        # Viewport not ready yet — retry once the app has settled
        import asyncio
        import omni.kit.app as kit_app

        async def _retry():
            app = kit_app.get_app()
            for _ in range(60):
                await app.next_update_async()
                vp = get_active_viewport()
                if vp:
                    try:
                        self._selection_disable_guard = disable_selection(vp)
                        print("[viewport_safety] disabled viewport selection (deferred, guard stored)")
                    except Exception as e:
                        print(f"[viewport_safety] deferred disable_selection failed: {e}")
                    return
            print("[viewport_safety] viewport never became available for disable_selection")

        try:
            self._retry_task = asyncio.ensure_future(_retry())
        except Exception:
            pass

    def _setup_tool_blocker(self):
        """
        Force viewport tools to "none" and block re-activation.
        Disables the transform gizmo without a frame loop.
        """
        try:
            import carb.settings as carb_settings

            settings = self._settings if self._settings else carb_settings.get_settings()
            if not settings:
                return

            current_tool_path = "/app/viewport/currentTool"
            modal_tool_active_path = "/app/tools/modal_tool_active"

            # Avoid double subscriptions
            if getattr(self, "_tool_blocker_subscriptions", None):
                return

            def _force_tools_off(*_args):
                try:
                    settings.set(current_tool_path, "none")
                    settings.set(modal_tool_active_path, False)
                except Exception:
                    pass

            _force_tools_off()

            self._tool_blocker_subscriptions = [
                settings.subscribe_to_node_change_events(current_tool_path, _force_tools_off),
                settings.subscribe_to_node_change_events(modal_tool_active_path, _force_tools_off),
            ]
            print("[viewport_safety] tool blocker installed (currentTool forced to none)")
        except Exception as e:
            print(f"[viewport_safety] error setting up tool blocker: {e}")

    def _setup_selection_clearer(self):
        """
        Clear selection on SELECTION_CHANGED so highlights/manipulators don't appear.
        """
        try:
            import omni.usd
            import carb.eventdispatcher

            def _on_selection_changed(event):
                try:
                    if hasattr(event, "type") and event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
                        ctx = omni.usd.get_context()
                        if ctx:
                            selection = ctx.get_selection()
                            if selection:
                                selected_paths = selection.get_selected_prim_paths()
                                if selected_paths:
                                    selection.clear_selected_prim_paths()
                except Exception:
                    pass

            ed = carb.eventdispatcher.get_eventdispatcher()
            self._selection_clearer_subscription = ed.observe_event(
                observer_name="younite.viewport_safety_extension/selection_clearer",
                event_name="omni.usd@stage_event",
                on_event=_on_selection_changed,
                order=999,
            )
            print("[viewport_safety] selection clearer installed")
        except Exception as e:
            print(f"[viewport_safety] error setting up selection clearer: {e}")

    def on_shutdown(self):
        self._selection_disable_guard = None
        self._selection_clearer_subscription = None
        self._tool_blocker_subscriptions = None
        try:
            task = getattr(self, "_retry_task", None)
            if task and hasattr(task, "cancel"):
                task.cancel()
        except Exception:
            pass
        self._retry_task = None
        self._settings = None

