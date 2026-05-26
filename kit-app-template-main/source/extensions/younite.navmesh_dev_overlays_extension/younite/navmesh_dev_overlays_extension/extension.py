"""Dev-only Kit viewport overlays for dual-mode NavMesh (debug mesh + stair diff)."""

from __future__ import annotations

import omni.ext


class NavMeshDevOverlaysExtension(omni.ext.IExt):
    """Subscribes to web toggles and dual-bake / mode events; owns overlay services."""

    def on_startup(self, _ext_id: str):
        self._subs = []

        from younite.navmesh_route_extension.navmesh_route_bridge import (
            get_navmesh_mode_cache_for_dev,
            schedule_navmesh_rebake_if_idle,
        )
        from younite.messaging_core_extension.message_utils import (
            normalize_event_payload,
            register_outbound_events,
        )
        from .services.accessibility_diff_service import AccessibilityDiffService
        from .services.active_navmesh_overlay_service import ActiveNavMeshOverlayService

        mode_cache = get_navmesh_mode_cache_for_dev()
        if mode_cache is None:
            print(
                "[navmesh_dev_overlays] WARNING: NavMesh mode cache bridge is unset — "
                "ensure younite.navmesh_route_extension loaded before this extension."
            )

        self._diff_service = AccessibilityDiffService(mode_cache)
        self._navmesh_overlay = ActiveNavMeshOverlayService(mode_cache)

        try:
            register_outbound_events(
                [
                    "accessibilityDiffStatus",
                    "navmeshDebugStatus",
                ]
            )
        except Exception as exc:
            print(f"[navmesh_dev_overlays] register_outbound_events failed: {exc}")

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _alias(name: str) -> None:
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass

            def _observe(name: str, handler) -> None:
                _alias(name)
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.navmesh_dev_overlays_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            def _after_enable(service, log_prefix: str) -> None:
                mc = get_navmesh_mode_cache_for_dev()
                if mc is not None and mc.is_ready():
                    try:
                        service.recompute()
                    except Exception as exc:
                        print(f"[{log_prefix}] recompute after enable failed: {exc}")
                    return
                schedule_navmesh_rebake_if_idle()

            def _on_accessibility_diff_show(evt):
                try:
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    vis = bool(payload.get("visible", False))
                    self._diff_service.set_feature_enabled(vis)
                    if vis:
                        _after_enable(self._diff_service, "ACCESS_DIFF")
                except Exception as exc:
                    print(f"[navmesh_dev_overlays] accessibilityDiffShow failed: {exc}")

            def _on_navmesh_debug_show(evt):
                try:
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    vis = bool(payload.get("visible", False))
                    self._navmesh_overlay.set_feature_enabled(vis)
                    if vis:
                        _after_enable(self._navmesh_overlay, "NAVMESH_DEBUG")
                except Exception as exc:
                    print(f"[navmesh_dev_overlays] navmeshDebugShow failed: {exc}")

            def _on_dual_bake_complete(evt):
                try:
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    if not bool(payload.get("success", False)):
                        return
                    if self._diff_service.is_feature_enabled():
                        try:
                            self._diff_service.recompute()
                        except Exception as exc:
                            print(f"[navmesh_dev_overlays] diff recompute after bake failed: {exc}")
                    if self._navmesh_overlay.is_feature_enabled():
                        try:
                            self._navmesh_overlay.recompute()
                        except Exception as exc:
                            print(
                                f"[navmesh_dev_overlays] debug overlay recompute after bake failed: {exc}"
                            )
                except Exception as exc:
                    print(f"[navmesh_dev_overlays] navmeshDualBakeComplete handler failed: {exc}")

            def _on_navmesh_mode_status(evt):
                try:
                    payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                    if str(payload.get("status") or "") != "ready":
                        return
                    if self._navmesh_overlay.is_feature_enabled():
                        try:
                            self._navmesh_overlay.recompute()
                        except Exception as exc:
                            print(
                                f"[navmesh_dev_overlays] debug overlay recompute after mode failed: {exc}"
                            )
                except Exception as exc:
                    print(f"[navmesh_dev_overlays] navmeshModeStatus handler failed: {exc}")

            _observe("accessibilityDiffShow", _on_accessibility_diff_show)
            _observe("navmeshDebugShow", _on_navmesh_debug_show)
            _observe("navmeshDualBakeComplete", _on_dual_bake_complete)
            _observe("navmeshModeStatus", _on_navmesh_mode_status)

        except Exception as exc:
            print(f"[navmesh_dev_overlays] event subscribe failed: {exc}")

    def on_shutdown(self):
        self._subs.clear()
        self._diff_service = None
        self._navmesh_overlay = None
