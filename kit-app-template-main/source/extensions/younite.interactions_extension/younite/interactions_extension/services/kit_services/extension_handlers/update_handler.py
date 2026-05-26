"""Per-frame update loop (GLOBAL_EVENT_UPDATE) and small helpers."""
from __future__ import annotations


class _UpdateHandler:
    """Base supplying tick/update subscription and frame helpers."""

    def _start_update_loop(self) -> None:
        try:
            import carb.eventdispatcher
            import omni.kit.app

            ed = carb.eventdispatcher.get_eventdispatcher()
            self._update_sub = ed.observe_event(
                observer_name="younite.interactions_extension/update",
                event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
                on_event=self._on_update,
                order=0,
            )
        except Exception as e:
            self._update_sub = None
            print(f"[interactions] update loop start failed: {e}")

    def _on_update(self, _e=None):
        try:
            self._rotation.tick()
        except Exception:
            pass
        try:
            if self._marker_service:
                self._marker_service.update()
        except Exception:
            pass
        try:
            if self._approach_service:
                self._approach_service.update()
        except Exception:
            pass

        if self._auto_move_active:
            return

        try:
            if self._spatial_service:
                self._spatial_service.update()
        except Exception:
            pass

        try:
            self._nearest_npc.update(self._npc_registry)
        except Exception:
            pass
        try:
            self._nearest_icon.update(self._icon_registry)
        except Exception:
            pass

        if not self._enabled_range:
            return
        try:
            import carb.settings

            if not carb.settings.get_settings().get("/younite/client/connected"):
                return
        except Exception:
            pass

        try:
            import omni.usd
            import omni.kit.viewport.utility as vp_util

            usd_context = omni.usd.get_context()
            stage = usd_context.get_stage() if usd_context else None
            viewport = vp_util.get_active_viewport()
            viewport_api = viewport.viewport_api if viewport and hasattr(viewport, "viewport_api") else viewport
        except Exception:
            return

        now_ms = self._now_ms()

        try:
            result = self._config_loader.maybe_reload(
                now_ms=now_ms,
                stage=stage,
                media_content_theme=self._read_media_content_theme(),
            )
            if result is not None:
                self._apply_loaded_config(result)
        except Exception:
            pass

        try:
            self._projectables_loop.tick(
                now_ms=now_ms,
                stage=stage,
                viewport_api=viewport_api,
                usd_context=usd_context,
                projectable_points=self._projectable_points,
            )
        except Exception:
            pass

    def _clear_interaction_state(self) -> None:
        try:
            self._nearest_npc.clear_and_dispatch()
            self._nearest_icon.clear_and_dispatch()
            self._projectables_loop.clear_sent()
        except Exception:
            pass

    def _get_player_world_pos(self):
        pls = getattr(self, "_player_location_service", None)
        return pls.get_player_world_position() if pls else None

    @staticmethod
    def _now_ms() -> int:
        try:
            import time

            return int(time.time() * 1000)
        except Exception:
            return 0

    @staticmethod
    def _read_media_content_theme() -> str:
        try:
            import carb.settings as cs

            v = cs.get_settings().get("/younite/media/contentTheme")
            if v:
                return str(v).strip() or "horseshow"
        except Exception:
            pass
        return "horseshow"
