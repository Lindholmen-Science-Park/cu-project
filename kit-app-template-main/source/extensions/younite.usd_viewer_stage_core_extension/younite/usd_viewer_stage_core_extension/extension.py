import omni.ext

from .runtime_config_service import configure_runtime
from .stage_loading import LoadingManager
from .stage_loading_phase import stage_loading_phase, PHASE_PREPARING_LIGHTS, PHASE_PREPARING_NAVMESH, PHASE_READY
from .stage_management import StageManager
from .stage_readiness import stage_readiness
from .stage_watcher import StageWatcher
from younite.weather_and_seasons_extension.fog_service import FogService
from .services.kit_services.teleport_service import TeleportService
from .services.kit_services.camera_service import CameraService
from .services.core_services.initial_stage_open_service import InitialStageOpenService
from .services.core_services.ui_stage_service import UiStageService
from .services.core_services.sky_control_service import SkyControlService
from .services.core_services.feature_commands_service import FeatureCommandsService
from .services.core_services.resolution_service import ResolutionService
from .services.core_services.player_ready_service import PlayerReadyService
from .services.core_services.cesium_tile_orchestrator import CesiumTileOrchestrator
from .services.core_services.geo_coordinate_service import GeoCoordinateService
from .services.core_services.world_state_sync_service import WorldStateSyncService


class StageCoreExtension(omni.ext.IExt):
    """
    Stage core extension:
    - applies global runtime settings early (streaming input, simulationEnabled)
    - installs stage event watcher BEFORE SetupExtension opens the stage
    - runs init timing and sets settings-backed readyForPlayer gate
    - waits for PlayerCore readiness and then marks stage initialized + emits scene.loaded

    Diagnostics: use print() (carb logs not reliably visible).
    """

    PLAYER_READY_SETTING = "/younite/player/ready"
    READY_FOR_PLAYER_SETTING = "/younite/player/readyForPlayer"
    APP_READY_SETTING = "/younite/app/ready"

    # App bootstrap settings (moved here from SetupExtension; Option B)
    AUTO_LOAD_USD_SETTING = "/app/auto_load_usd"
    WARMUP_MODE_SETTING = "/app/warmupMode"
    EMPTY_STAGE_ON_START_SETTING = "/app/content/emptyStageOnStart"
    COMMAND_MACRO_FILE_SETTING = "/exts/omni.kit.command_macro.core/macro_file"

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id

        # settings
        try:
            import carb.settings as carb_settings
            self._settings = carb_settings.get_settings()
        except Exception:
            self._settings = None

        # tasks
        self._tasks = []

        # Apply runtime config early (before stage open)
        try:
            configure_runtime(settings=self._settings)
            print("[stage_core] runtime configured")
        except Exception as e:
            print(f"[stage_core] runtime config failed: {e}")

        # Enable viewport safety early to prevent highlight/selection/manipulators
        try:
            import omni.kit.app as kit_app
            app = kit_app.get_app()
            ext_mgr = app.get_extension_manager()
            ext_mgr.set_extension_enabled_immediate("younite.viewport_safety_extension", True)
            print("[stage_core] enabled viewport safety extension")
        except Exception:
            pass

        # Core managers that existed in the monolith
        self._loading_manager = LoadingManager()
        self._stage_manager = StageManager()

        # Stage-owned feature services
        self._fog = FogService()
        self._teleport = TeleportService()
        try:
            from .teleport_registry import set_teleport_service
            set_teleport_service(self._teleport)
        except Exception:
            pass
        self._camera = CameraService(self._stage_manager, teleport_service=self._teleport)

        # World state sync (central registry — must be created before services that write to it)
        self._world_state_sync = WorldStateSyncService()
        try:
            from .services.core_services.world_state_sync_service import register_world_state_sync_service

            register_world_state_sync_service(self._world_state_sync)
        except Exception:
            pass

        # Core services (split out of this extension)
        self._ui_stage_service = UiStageService(
            stage_manager=self._stage_manager, stage_readiness=stage_readiness, track_task_cb=self._track_task,
            world_state=self._world_state_sync,
        )
        self._sky_control_service = SkyControlService(
            stage_manager=self._stage_manager, stage_readiness=stage_readiness, track_task_cb=self._track_task,
            world_state=self._world_state_sync,
        )
        self._feature_commands_service = FeatureCommandsService(
            settings=self._settings, fog=self._fog, camera=self._camera, stage_manager=self._stage_manager,
            world_state=self._world_state_sync,
        )
        self._resolution_service = ResolutionService(settings=self._settings)
        self._player_ready_service = PlayerReadyService(
            settings=self._settings,
            player_ready_setting=self.PLAYER_READY_SETTING,
            app_ready_setting=self.APP_READY_SETTING,
        )
        self._initial_stage_open_service = InitialStageOpenService(
            settings=self._settings,
            auto_load_usd_setting=self.AUTO_LOAD_USD_SETTING,
            warmup_mode_setting=self.WARMUP_MODE_SETTING,
            empty_stage_on_start_setting=self.EMPTY_STAGE_ON_START_SETTING,
            command_macro_file_setting=self.COMMAND_MACRO_FILE_SETTING,
            track_task_cb=self._track_task,
            frame_delay=6,
        )
        self._cesium_orchestrator = CesiumTileOrchestrator(track_task_cb=self._track_task)
        self._geo_coordinate_service = GeoCoordinateService()
        self._geo_coordinate_service.start()

        # Reset app/player readiness flags on startup
        try:
            s = self._settings
            if s:
                s.set(self.PLAYER_READY_SETTING, False)
                s.set(self.READY_FOR_PLAYER_SETTING, False)
                s.set(self.APP_READY_SETTING, False)
                s.set("/younite/client/connected", False)
        except Exception:
            pass

        # Start stage watcher early (critical ordering)
        self._watcher = StageWatcher(settings=self._settings, track_task_cb=self._track_task)
        self._watcher.start()

        # Start always-on services
        try:
            self._world_state_sync.start()
        except Exception:
            pass
        try:
            self._ui_stage_service.start()
        except Exception:
            pass
        try:
            self._sky_control_service.start()
        except Exception:
            pass
        try:
            self._feature_commands_service.start()
        except Exception:
            pass
        try:
            self._resolution_service.start()
        except Exception:
            pass
        try:
            self._cesium_orchestrator.start()
        except Exception:
            pass

        # Observe player readiness and coordinate appReady behavior
        try:
            self._player_ready_service.start(self._on_player_ready)
        except Exception:
            pass

        # Option B: StageCore owns initial stage open (SetupExtension is UI/layout only).
        try:
            self._initial_stage_open_service.start()
        except Exception:
            pass

    def _track_task(self, task):
        try:
            self._tasks.append(task)
        except Exception:
            pass
        return task

    def _on_player_ready(self):
        # NOTE: mark_initialized() is deferred to _finalize_scene_load so that
        # ui_stage_service._on_ui_ready won't dispatch scene.loaded prematurely
        # while we are still waiting for the MDL shader to compile.

        # Apply default sky/light immediately so lighting params are set
        # while the loading screen is still visible.
        try:
            import carb.eventdispatcher as _ed
            ed = _ed.get_eventdispatcher()
            try:
                import omni.kit.app as _kit_app
                import carb as _carb
                _kit_app.register_event_alias(_carb.events.type_from_string("skyControlRequest"), "skyControlRequest")
            except Exception:
                pass
            default_payload = {"timeOfDay": 12.0, "dayOfYear": 187, "cumulusEnabled": True}
            ed.dispatch_event("skyControlRequest", default_payload)
        except Exception as e:
            print(f"[stage_core] could not dispatch default sky control: {e}")

        # Mark appReady (feature extensions are now loaded via .kit file dependencies with order=1200)
        try:
            if self._settings:
                self._settings.set(self.APP_READY_SETTING, True)
        except Exception:
            pass

        # Keep the loading screen visible while lights initialise.
        # scene.loaded is dispatched inside _finalize_scene_load, NOT here.
        try:
            import asyncio
            self._track_task(asyncio.ensure_future(self._finalize_scene_load()))
        except Exception:
            pass

    async def _finalize_scene_load(self):
        """Wait for MDL compilation, cycle lights off/on, then reveal the scene.

        The CumulusLight procedural sky MDL compiles asynchronously.  If the
        RTX renderer evaluates the DomeLight before compilation finishes it
        caches a black environment texture.  We keep the loading screen up
        while we wait for the MDL (3 s), then cycle every UsdLux light
        invisible -> visible via ``MakeVisible()`` on the session layer.
        ``MakeVisible()`` writes an explicit ``visibility = inherited``
        opinion on the session layer which survives subsequent Hydra
        invalidations (NavMesh bake, camera switches, etc.), unlike the
        previous ``RemoveProperty`` approach which could silently fail and
        leave lights stuck as invisible.
        """
        import asyncio
        import omni.kit.app as _kit
        import omni.usd

        MDL_COMPILE_WAIT = 3.0
        FRAMES_OFF = 8
        FRAMES_ON = 8

        app = _kit.get_app()

        try:
            stage_loading_phase.set_phase(PHASE_PREPARING_LIGHTS, "Preparing lights...")

            await asyncio.sleep(MDL_COMPILE_WAIT)

            stage = omni.usd.get_context().get_stage()

            try:
                if self._geo_coordinate_service:
                    self._geo_coordinate_service.load_from_stage()
            except Exception as e:
                print(f"[stage_core] geo coordinate service load failed: {e}")

            if stage:
                from pxr import Sdf, Usd, UsdGeom, UsdLux

                session = stage.GetSessionLayer()

                light_paths = []
                for prim in stage.Traverse():
                    if prim.HasAPI(UsdLux.LightAPI):
                        light_paths.append(prim.GetPath())

                if light_paths:
                    with Usd.EditContext(stage, session):
                        with Sdf.ChangeBlock():
                            for path in light_paths:
                                prim = stage.GetPrimAtPath(path)
                                if prim:
                                    UsdGeom.Imageable(prim).GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)

                    for _ in range(FRAMES_OFF):
                        await app.next_update_async()

                    with Usd.EditContext(stage, session):
                        with Sdf.ChangeBlock():
                            for path in light_paths:
                                prim = stage.GetPrimAtPath(path)
                                if prim:
                                    UsdGeom.Imageable(prim).MakeVisible()

                    for _ in range(FRAMES_ON):
                        await app.next_update_async()

                    print(f"[stage_core] lights initialised — {len(light_paths)} UsdLux prims cycled")
                else:
                    print("[stage_core] no UsdLux lights found — skipping light init")

            try:
                if not stage_readiness.is_initialized():
                    stage_readiness.mark_initialized()
            except Exception:
                pass

            import carb
            import carb.eventdispatcher as _ed
            ed = _ed.get_eventdispatcher()
            scene_path = ""
            if stage:
                root = stage.GetRootLayer()
                scene_path = getattr(root, "identifier", "") or ""

            current_vt = str(carb.settings.get_settings().get("/younite/camera/viewType") or "firstPerson")

            # Block scene.loaded until both NavMesh modes (walking + wheelchair)
            # are baked so the user can't rush through onboarding and click
            # ground while the dual bake is still running (which would silently
            # resolve against the wrong mesh). Bird's-eye start doesn't need
            # navmesh so we skip the wait there — the bake will kick off when
            # the user later enters first-person via `_async_first_person_enter`.
            if current_vt != "birdEye":
                try:
                    from .first_person_navmesh_bridge import await_first_person_navmesh_prepare

                    stage_loading_phase.set_phase(
                        PHASE_PREPARING_NAVMESH,
                        "Preparing navigation (walking + wheelchair)...",
                    )
                    await await_first_person_navmesh_prepare()
                    print("[stage_core] dual-mode navmesh ready")
                except Exception as e:
                    print(f"[stage_core] navmesh wait failed: {e}")

            stage_loading_phase.set_phase(PHASE_READY, "Ready")
            scene_loaded_payload = {"scene": scene_path, "success": True, "viewType": current_vt}

            ed.dispatch_event("scene.loaded", scene_loaded_payload)
            print(f"[stage_core] scene.loaded dispatched (lights ready, viewType={current_vt})")

            try:
                if self._settings:
                    self._settings.set(self.READY_FOR_PLAYER_SETTING, True)
            except Exception:
                pass

            # Retry for late-connecting clients
            await asyncio.sleep(1.5)
            ed.dispatch_event("scene.loaded", scene_loaded_payload)
            stage_loading_phase.set_phase(PHASE_READY, "Ready")
            print("[stage_core] scene.loaded re-dispatched (retry)")

        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[stage_core] finalize_scene_load failed: {e}")
            try:
                stage_loading_phase.set_phase(PHASE_READY, "Ready")
                import carb
                import carb.eventdispatcher as _ed
                ed = _ed.get_eventdispatcher()
                fallback_vt = str(carb.settings.get_settings().get("/younite/camera/viewType") or "firstPerson")
                ed.dispatch_event("scene.loaded", {"scene": "", "success": True, "viewType": fallback_vt})
            except Exception:
                pass

    def on_shutdown(self):
        # Stop geo coordinate service
        try:
            if getattr(self, "_geo_coordinate_service", None):
                self._geo_coordinate_service.stop()
        except Exception:
            pass
        self._geo_coordinate_service = None

        # Stop Cesium orchestrator
        try:
            if getattr(self, "_cesium_orchestrator", None):
                self._cesium_orchestrator.stop()
        except Exception:
            pass
        self._cesium_orchestrator = None

        # Stop always-on services first (unsubscribe events)
        try:
            if getattr(self, "_player_ready_service", None):
                self._player_ready_service.stop()
        except Exception:
            pass
        self._player_ready_service = None

        try:
            if getattr(self, "_feature_commands_service", None):
                self._feature_commands_service.stop()
        except Exception:
            pass
        self._feature_commands_service = None

        try:
            if getattr(self, "_sky_control_service", None):
                self._sky_control_service.stop()
        except Exception:
            pass
        self._sky_control_service = None

        try:
            if getattr(self, "_ui_stage_service", None):
                self._ui_stage_service.stop()
        except Exception:
            pass
        self._ui_stage_service = None

        try:
            if getattr(self, "_resolution_service", None):
                self._resolution_service.stop()
        except Exception:
            pass
        self._resolution_service = None

        try:
            if getattr(self, "_initial_stage_open_service", None):
                self._initial_stage_open_service.stop()
        except Exception:
            pass
        self._initial_stage_open_service = None

        try:
            if getattr(self, "_world_state_sync", None):
                self._world_state_sync.stop()
        except Exception:
            pass
        try:
            from .services.core_services.world_state_sync_service import register_world_state_sync_service

            register_world_state_sync_service(None)
        except Exception:
            pass
        self._world_state_sync = None

        # Cancel tasks
        try:
            for t in getattr(self, "_tasks", []) or []:
                try:
                    if hasattr(t, "cancel"):
                        t.cancel()
                except Exception:
                    pass
        except Exception:
            pass
        self._tasks = []

        # Stop stage watcher
        try:
            if getattr(self, "_watcher", None):
                self._watcher.stop()
        except Exception:
            pass
        self._watcher = None

        # Managers shutdown
        try:
            if getattr(self, "_loading_manager", None):
                self._loading_manager.on_shutdown()
        except Exception:
            pass
        self._loading_manager = None

        try:
            if getattr(self, "_stage_manager", None):
                self._stage_manager.on_shutdown()
        except Exception:
            pass
        self._stage_manager = None

        self._fog = None
        try:
            from .teleport_registry import set_teleport_service
            set_teleport_service(None)
        except Exception:
            pass
        self._teleport = None
        self._camera = None
        self._settings = None

