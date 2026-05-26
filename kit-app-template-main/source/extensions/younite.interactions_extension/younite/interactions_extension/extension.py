"""InteractionsExtension — lifecycle & coordinator for the interactions subsystem.

Implementation is split across :mod:`services.kit_services` (services, config loader,
extension handler bases) and focused modules at the package root (``usd_helpers``, etc.).
"""
from __future__ import annotations

import omni.ext

from .services.kit_services.extension_handlers.config_handler import _ConfigHandler
from .services.kit_services.extension_handlers.event_handler import _InteractionEventHandler
from .services.kit_services.extension_handlers.update_handler import _UpdateHandler


class InteractionsExtension(_ConfigHandler, _InteractionEventHandler, _UpdateHandler, omni.ext.IExt):
    """Unified spatial interactions extension."""

    UPDATE_EVENT = "uiInteractionBoxesUpdate"
    WEB_ACTION_EVENT = "interactionTriggered"
    NAV_REQUEST_EVENT = "younite.navigation.requestPoint"
    POINT_TRIGGERED_EVENT = "interactionPointTriggered"
    POINTS_SYNC_EVENT = "interactionPointsSync"
    NPC_NEAREST_EVENT = "npcNearestUpdate"
    ICON_NEAREST_EVENT = "iconNearestUpdate"

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs: list = []
        self._update_sub = None
        self._stage_sub = None

        self._settings = None
        self._enabled_range = True
        min_interval_ms = 100
        try:
            import carb.settings as carb_settings

            self._settings = carb_settings.get_settings()
            self._enabled_range = bool(
                self._settings.get("/exts/younite.interactions_extension/range_overlays_enabled")
            )
            min_interval_ms = int(self._settings.get("/exts/younite.interactions_extension/update_interval_ms") or 100)
        except Exception:
            pass

        from .services.kit_services.action_handler_service import ActionHandlerService
        from .services.kit_services.approach_service import ApproachService
        from .services.kit_services.click_router import ClickRouter
        from .services.kit_services.config_loader import ConfigLoader
        from .services.kit_services.interaction_marker_service import InteractionMarkerService
        from .services.kit_services.nearest_entity_tracker import NearestEntityTracker
        from .services.kit_services.projectables_loop import ProjectablesLoop
        from .services.kit_services.projection_service import ProjectionService
        from .services.kit_services.rotation_service import RotationService
        from .services.kit_services.spatial_trigger_service import SpatialTriggerService
        from . import usd_helpers
        from younite.messaging_core_extension.message_utils import register_outbound_events

        self._usd_helpers = usd_helpers

        self._projection = ProjectionService()
        self._rotation = RotationService()
        self._config_loader = ConfigLoader(settings=self._settings)
        self._marker_service = InteractionMarkerService()

        def _dispatch(name: str, payload: dict) -> None:
            try:
                import carb.eventdispatcher

                carb.eventdispatcher.get_eventdispatcher().dispatch_event(
                    name, payload if isinstance(payload, dict) else {}
                )
            except Exception:
                pass

        self._action_handler = ActionHandlerService(
            dispatch_event=_dispatch, emit_web_event=_dispatch
        )

        from younite.usd_viewer_player_core_extension import extension as _player_core_mod

        _instance = getattr(_player_core_mod, "_instance", None)
        self._player_location_service = _instance.get_player_location_service() if _instance else None

        self._spatial_service = SpatialTriggerService(
            get_player_position=self._get_player_world_pos,
        )
        self._spatial_service.on_enter(self._on_trigger_entered)

        def _safe_mpu():
            try:
                import omni.usd

                stage = omni.usd.get_context().get_stage()
                return usd_helpers.get_stage_meters_per_unit(stage) if stage else 0.01
            except Exception:
                return 0.01

        self._approach_service = ApproachService(
            get_player_pos=self._get_player_world_pos,
            get_meters_per_unit=_safe_mpu,
        )

        self._nearest_npc = NearestEntityTracker(
            event_name=self.NPC_NEAREST_EVENT,
            payload_key="npcConfig",
            registry_cfg_field="npc_config",
            get_player_pos=self._get_player_world_pos,
        )
        self._nearest_icon = NearestEntityTracker(
            event_name=self.ICON_NEAREST_EVENT,
            payload_key="iconConfig",
            registry_cfg_field="icon_config",
            get_player_pos=self._get_player_world_pos,
            coin_poi_max_visible_m=50.0,
        )

        self._projectables_loop = ProjectablesLoop(
            projection_service=self._projection,
            get_player_pos=self._get_player_world_pos,
            update_event_name=self.UPDATE_EVENT,
            min_interval_ms=min_interval_ms,
        )

        self._click_router = ClickRouter(
            action_handler=self._action_handler,
            approach_service=self._approach_service,
            marker_service=self._marker_service,
            rotation_service=self._rotation,
            get_player_pos=self._get_player_world_pos,
            get_click_points_by_path=lambda: self._click_points_by_path,
        )

        self._all_points: list = []
        self._projectable_points: list = []
        self._click_points_by_path: dict = {}
        self._npc_registry: dict = {}
        self._icon_registry: dict = {}

        self._auto_move_active: bool = False

        try:
            register_outbound_events([
                self.UPDATE_EVENT,
                self.WEB_ACTION_EVENT,
                self.POINTS_SYNC_EVENT,
                self.POINT_TRIGGERED_EVENT,
                self.NPC_NEAREST_EVENT,
                self.ICON_NEAREST_EVENT,
            ])
        except Exception:
            pass

        self._subscribe_events()
        self._subscribe_stage_events()
        try:
            from .services.kit_services.avatar_nav_exclusion import (
                subscribe_avatar_nav_exclusion_events,
            )

            subscribe_avatar_nav_exclusion_events(self._subs)
        except Exception:
            pass
        self._start_update_loop()

        try:
            print(f"[interactions] started (intervalMs={min_interval_ms})")
        except Exception:
            pass

    def on_shutdown(self):
        self._stage_sub = None
        self._subs.clear()
        self._update_sub = None

        def _safe(label: str, fn) -> None:
            try:
                fn()
            except Exception as e:
                print(f"[interactions] shutdown {label}: {e}")

        if getattr(self, "_marker_service", None):
            _safe("markers", self._marker_service.destroy)
        self._marker_service = None

        if getattr(self, "_approach_service", None):
            _safe("approach", self._approach_service.shutdown)
        self._approach_service = None

        if getattr(self, "_spatial_service", None):
            _safe("spatial", self._spatial_service.clear_all)
        self._spatial_service = None

        if getattr(self, "_rotation", None):
            _safe("rotation", self._rotation.clear)
        self._rotation = None

        self._projection = None
        self._action_handler = None
        self._player_location_service = None
        self._click_router = None
        self._projectables_loop = None
        self._nearest_npc = None
        self._nearest_icon = None
        self._config_loader = None
        self._settings = None
