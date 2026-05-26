"""
Kit-side viewport blur via RTX Depth of Field.

Standalone service — not wired into the extension by default.
To activate, subscribe to ``chatBlur.enable`` / ``chatBlur.disable``
events and call :meth:`BlurService.enable` / :meth:`BlurService.disable`,
or wire the convenience :meth:`BlurService.register_events` helper which
does both in one step.

Web side sends::

    sendCustomMessage('chatBlur.enable',  {})
    sendCustomMessage('chatBlur.disable', {})

DOF is controlled via USD attributes on the session layer:
  - RenderProduct ``omni:rtx:post:dof:enabled`` (bool)
  - Camera ``fStop`` (float) — lower = more blur
  - Camera ``focusDistance`` (float) — scene-unit distance to focus plane
"""

from __future__ import annotations

_RENDER_PRODUCT_PATH = (
    "/Render/OmniverseKit/HydraTextures/"
    "omni_kit_widget_viewport_ViewportTexture_0"
)

_TAG = "[blur_service]"


class BlurService:
    """Toggle RTX DOF blur on the active viewport camera."""

    def __init__(self):
        self._saved: dict | None = None
        self._subs: list = []

    # -- public API -----------------------------------------------------------

    def enable(self) -> None:
        """Apply heavy DOF blur so the streamed frame is fully out of focus."""
        self._apply_dof_blur()

    def disable(self) -> None:
        """Restore the original DOF / camera values."""
        self._restore_dof()

    def register_events(self) -> None:
        """Subscribe to ``chatBlur.enable`` / ``chatBlur.disable`` events.

        Call once during extension startup.  The subscriptions are stored
        internally and cleaned up by :meth:`unregister_events`.
        """
        import carb
        import carb.eventdispatcher
        import omni.kit.app as kit_app

        ed = carb.eventdispatcher.get_eventdispatcher()

        for evt_name in ("chatBlur.enable", "chatBlur.disable"):
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string(evt_name), evt_name,
                )
            except Exception:
                pass

        self._subs.append(
            ed.observe_event(
                observer_name="younite.ai_agent_extension/chatBlur.enable",
                event_name="chatBlur.enable",
                on_event=lambda _evt: self.enable(),
                order=0,
            )
        )
        self._subs.append(
            ed.observe_event(
                observer_name="younite.ai_agent_extension/chatBlur.disable",
                event_name="chatBlur.disable",
                on_event=lambda _evt: self.disable(),
                order=0,
            )
        )
        print(f"{_TAG} event subscriptions registered")

    def unregister_events(self) -> None:
        """Drop event subscriptions (call on extension shutdown)."""
        self._subs.clear()

    def shutdown(self) -> None:
        """Restore DOF and drop subscriptions."""
        self._restore_dof()
        self.unregister_events()

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _get_stage_and_edit_ctx():
        import omni.usd
        from pxr import Usd

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return None, None
        session = stage.GetSessionLayer()
        return stage, Usd.EditContext(stage, Usd.EditTarget(session))

    @staticmethod
    def _get_active_camera_path():
        try:
            from omni.kit.viewport.utility import get_active_viewport

            vp = get_active_viewport()
            if vp:
                return str(vp.get_active_camera())
        except Exception:
            pass
        return "/OmniverseKit_Persp"

    def _apply_dof_blur(self):
        try:
            from pxr import Sdf, UsdGeom  # noqa: F401

            stage, edit_ctx = self._get_stage_and_edit_ctx()
            if not stage:
                print(f"{_TAG} no stage — skipping blur enable")
                return

            cam_path = self._get_active_camera_path()
            cam_prim = stage.GetPrimAtPath(cam_path)
            rp_prim = stage.GetPrimAtPath(_RENDER_PRODUCT_PATH)

            saved: dict = {"cam_path": cam_path}
            if cam_prim and cam_prim.IsValid():
                for name in ("fStop", "focusDistance"):
                    attr = cam_prim.GetAttribute(name)
                    saved[f"cam:{name}"] = (
                        attr.Get() if attr and attr.HasValue() else None
                    )
            if rp_prim and rp_prim.IsValid():
                attr = rp_prim.GetAttribute("omni:rtx:post:dof:enabled")
                saved["rp:dof:enabled"] = (
                    attr.Get() if attr and attr.HasValue() else None
                )
            self._saved = saved

            with edit_ctx:
                if rp_prim and rp_prim.IsValid():
                    rp_prim.GetAttribute("omni:rtx:post:dof:enabled").Set(True)
                if cam_prim and cam_prim.IsValid():
                    cam_prim.GetAttribute("fStop").Set(0.02)
                    cam_prim.GetAttribute("focusDistance").Set(0.1)

            print(f"{_TAG} DOF blur enabled (cam={cam_path})")
        except Exception as exc:
            import traceback

            print(f"{_TAG} DOF blur enable failed: {exc}")
            traceback.print_exc()

    def _restore_dof(self):
        try:
            saved = self._saved
            if not saved:
                return

            stage, edit_ctx = self._get_stage_and_edit_ctx()
            if not stage:
                self._saved = None
                return

            cam_path = saved.get("cam_path", "/OmniverseKit_Persp")
            cam_prim = stage.GetPrimAtPath(cam_path)
            rp_prim = stage.GetPrimAtPath(_RENDER_PRODUCT_PATH)

            with edit_ctx:
                if rp_prim and rp_prim.IsValid():
                    orig = saved.get("rp:dof:enabled")
                    rp_prim.GetAttribute("omni:rtx:post:dof:enabled").Set(
                        orig if orig is not None else False
                    )
                if cam_prim and cam_prim.IsValid():
                    for name in ("fStop", "focusDistance"):
                        orig = saved.get(f"cam:{name}")
                        if orig is not None:
                            cam_prim.GetAttribute(name).Set(orig)
                        else:
                            cam_prim.GetAttribute(name).Clear()

            self._saved = None
            print(f"{_TAG} DOF blur disabled (restored)")
        except Exception as exc:
            import traceback

            print(f"{_TAG} DOF blur restore failed: {exc}")
            traceback.print_exc()
