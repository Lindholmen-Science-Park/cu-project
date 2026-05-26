"""Apply parsed ``interactions.json`` (LoadedConfig) to live services + web sync."""
from __future__ import annotations


class _ConfigHandler:
    """Base supplying config reload / apply / sync methods on InteractionsExtension."""

    def _force_reload_config(self) -> None:
        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
        except Exception:
            stage = None
        try:
            result = self._config_loader.maybe_reload(
                now_ms=self._now_ms(),
                stage=stage,
                media_content_theme=self._read_media_content_theme(),
                force=True,
            )
        except Exception:
            result = None
        if result is not None:
            self._apply_loaded_config(result)

    def _apply_loaded_config(self, cfg) -> None:
        self._all_points = cfg.all_points
        self._projectable_points = cfg.projectable_points
        self._click_points_by_path = cfg.click_points_by_path
        self._npc_registry = cfg.npc_registry
        self._icon_registry = cfg.icon_registry

        self._nearest_npc.reset()
        self._nearest_icon.reset()

        if self._spatial_service:
            self._spatial_service.clear_all()
            self._spatial_service.meters_per_unit = cfg.meters_per_unit

        for spec in cfg.spatial_triggers:
            self._spatial_service.add_trigger(
                trigger_id=spec.trigger_id,
                position=spec.position,
                trigger_type=spec.trigger_type,
                radius=spec.radius,
                radius_meters=spec.radius_meters,
                xz_only=spec.xz_only,
                one_shot=spec.one_shot,
                activation=spec.activation,
                behaviors=spec.behaviors,
                bounds=spec.bounds,
                active=spec.active,
            )

        if cfg.npc_marker_paths:
            try:
                self._marker_service.create_markers(cfg.npc_marker_paths, mode="npc")
            except Exception as e:
                print(f"[interactions] NPC marker error: {e}")
        if cfg.icon_marker_paths:
            try:
                self._marker_service.create_markers(cfg.icon_marker_paths, mode="icon")
            except Exception as e:
                print(f"[interactions] Icon marker error: {e}")
        try:
            self._marker_service.register_coin_spinners(cfg.coin_marker_paths)
        except Exception as e:
            print(f"[interactions] Coin spinner registration error: {e}")

        self._sync_to_web()

    def _sync_to_web(self) -> None:
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2(self.POINTS_SYNC_EVENT, {"points": self._all_points})
            print(f"[interactions] synced {len(self._all_points)} points to web")
        except Exception as e:
            print(f"[interactions] sync failed: {e}")
