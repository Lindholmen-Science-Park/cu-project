"""
Stage initialization coordinator (event-driven where SDK allows).

Sequence (single source of truth):
  1. OPENED          → stage_loading_phase: loading_assets "Loading assets..."
  2. ASSETS_LOADED   → stage_readiness.mark_assets_loaded
  3. Settle (up to N frames) — Hydra/instancers; no SDK "ready" event, so we wait up to
     SETTLE_FRAMES_AFTER_ASSETS with progress messages.
  4. INITIALIZING    → simulation enabled, terrain payloads, then settle for instanced geometry
     (up to SETTLE_FRAMES_BEFORE_PLAYER) with progress messages.
  5. Timeline play   → one frame for physics
  6. READY_FOR_PLAYER → set /younite/player/readyForPlayer (signal to PlayerCore)
  7. PlayerCore     → sets up character, then sets /younite/player/ready
  8. PlayerReadyService → mark_initialized, loading.phase ready, scene.loaded

User connecting immediately or during setup: they receive loading.phase at each step.
User connecting after ready: ui.ready returns current phase + scene.loaded.
"""

import asyncio

import carb
import omni.kit.app as kit_app

from .stage_readiness import stage_readiness
from .stage_loading_phase import (
    stage_loading_phase,
    PHASE_LOADING_ASSETS,
    PHASE_INITIALIZING,
    PHASE_READY_FOR_PLAYER,
    PHASE_IDLE,
)

# Max frames to wait when no SDK "ready" signal exists (Hydra/instancers). Tunable; replace with event when available.
SETTLE_FRAMES_AFTER_ASSETS = 60
SETTLE_FRAMES_BEFORE_PLAYER = 120
PROGRESS_UPDATE_INTERVAL = 15  # Update loading.phase message every N frames so user sees progress


class StageWatcher:
    """
    Central stage init coordinator: subscribes to USD stage events and runs the init
    sequence. Uses event-driven transitions (OPENED, ASSETS_LOADED) where the SDK
    provides them; uses bounded frame waits with progress only where no ready signal exists.
    """

    READY_FOR_PLAYER_SETTING = "/younite/player/readyForPlayer"

    def __init__(self, *, settings=None, track_task_cb=None):
        self._settings = settings
        self._track_task = track_task_cb or (lambda t: t)

        self._stage_opened = False
        self._assets_loaded = False
        self._timeline_started = False
        self._initialization_in_progress = False
        self._initialization_complete = False

        # Monotonically increasing counter; bumped on every CLOSED event so
        # stale async coroutines (from a previous stage) detect that the stage
        # changed underneath them and abort instead of corrupting the new
        # stage's initialization state.
        self._generation = 0

        self._stage_subscription = None

    def start(self):
        """Subscribe to stage events early (before SetupExtension opens the stage).

        Uses the legacy get_stage_event_stream() intentionally: this call
        activates the Events 1.0 → 2.0 bridge for ``omni.usd@stage_event``.
        Without at least one old-style subscriber, Events 2.0 observers in
        other extensions will never receive OPENED / ASSETS_LOADED.  This
        single subscriber therefore keeps one deprecation warning but enables
        all downstream Events 2.0 stage-event observers to work.
        """
        try:
            import omni.usd

            usd_context = omni.usd.get_context()
            self._stage_subscription = usd_context.get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_event, name="StageCore Stage Event Watcher"
            )

            # Initialize the settings-backed gate to a known value
            try:
                s = self._settings if self._settings else carb.settings.get_settings()
                s.set(self.READY_FOR_PLAYER_SETTING, False)
            except Exception:
                pass

            # If stage already open, mark it but still wait for ASSETS_LOADED
            stage = usd_context.get_stage()
            if stage:
                self._stage_opened = True
        except Exception as e:
            print(f"[stage_core] stage watcher start failed: {e}")

    def stop(self):
        self._stage_subscription = None
        self._track_task = None

    def _on_stage_event(self, event):
        try:
            import omni.usd

            event_type = event.type if hasattr(event, "type") else None
            if event_type is None:
                return

            if event_type == int(omni.usd.StageEventType.OPENED):
                print("[stage_core] [STAGE] ✓ Stage OPENED")
                self._stage_opened = True
                try:
                    stage_readiness.mark_opened()
                except Exception:
                    pass
                try:
                    stage_loading_phase.set_phase(PHASE_LOADING_ASSETS, "Loading assets...")
                except Exception:
                    pass

            elif event_type == int(omni.usd.StageEventType.ASSETS_LOADED):
                if self._assets_loaded and self._initialization_complete:
                    return
                self._assets_loaded = True
                try:
                    stage_readiness.mark_assets_loaded()
                except Exception:
                    pass
                gen = self._generation
                self._track_task(asyncio.ensure_future(self._wait_then_initialize(gen)))

            elif event_type == int(omni.usd.StageEventType.CLOSED):
                self._generation += 1
                self._stage_opened = False
                self._assets_loaded = False
                self._timeline_started = False
                self._initialization_in_progress = False
                self._initialization_complete = False
                try:
                    stage_readiness.mark_closed()
                except Exception:
                    pass
                try:
                    stage_loading_phase.set_phase(PHASE_IDLE, "Stage closed")
                except Exception:
                    pass
                try:
                    s = self._settings if self._settings else carb.settings.get_settings()
                    s.set(self.READY_FOR_PLAYER_SETTING, False)
                except Exception:
                    pass
        except Exception:
            pass

    async def _wait_frames_with_progress(self, n_frames: int, phase: str, message_prefix: str, gen: int) -> bool:
        """Wait up to n_frames, updating loading.phase message periodically.

        Returns False if the generation changed (stage closed) during the wait,
        meaning the caller should abort.
        """
        app = kit_app.get_app()
        for i in range(n_frames):
            await app.next_update_async()
            if self._generation != gen:
                print(f"[stage_core] aborting stale '{message_prefix}' wait (generation changed)")
                return False
            if (i + 1) % PROGRESS_UPDATE_INTERVAL == 0 or i == n_frames - 1:
                try:
                    stage_loading_phase.set_phase(phase, f"{message_prefix} ({i + 1}/{n_frames})")
                except Exception:
                    pass
        return True

    async def _wait_then_initialize(self, gen: int):
        try:
            try:
                stage_loading_phase.set_phase(
                    PHASE_LOADING_ASSETS,
                    f"Preparing scene (Hydra/instancers, up to {SETTLE_FRAMES_AFTER_ASSETS} frames)...",
                )
            except Exception:
                pass
            print(f"[stage_core] ⏳ Waiting for Hydra/instancers (up to {SETTLE_FRAMES_AFTER_ASSETS} frames)...")
            ok = await self._wait_frames_with_progress(
                SETTLE_FRAMES_AFTER_ASSETS,
                PHASE_LOADING_ASSETS,
                "Preparing scene",
                gen,
            )
            if not ok:
                return
            self._check_and_start_initialization(gen)
        except Exception as e:
            print(f"[stage_core] wait_then_initialize error: {e}")
            if self._generation == gen:
                self._check_and_start_initialization(gen)

    def _check_and_start_initialization(self, gen: int):
        if self._generation != gen:
            return
        if self._initialization_complete or self._initialization_in_progress:
            return
        print(f"[stage_core] init readiness: opened={self._stage_opened}, assetsLoaded={self._assets_loaded}")
        if self._stage_opened and self._assets_loaded:
            self._track_task(asyncio.ensure_future(self._initialize_after_loading(gen)))

    def _ensure_terrain_payloads_loaded(self):
        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                print("[stage_core] ⚠️ No stage for terrain payload load")
                return
            terrain_paths = [
                "/main_scene/World/City_tile_01/Root/_0071_CU_DT_8km2_Terrain_Generation",
                "/World/City_tile_01/Root/_0071_CU_DT_8km2_Terrain_Generation",
            ]
            for path in terrain_paths:
                prim = stage.GetPrimAtPath(path)
                if prim and prim.IsValid():
                    if prim.HasPayload() and not prim.IsLoaded():
                        prim.Load()
                        print(f"[stage_core] ✓ Loaded terrain payload at {path}")
                    break
        except Exception as e:
            print(f"[stage_core] terrain payload load error: {e}")

    async def _initialize_after_loading(self, gen: int):
        try:
            if self._initialization_in_progress:
                return
            self._initialization_in_progress = True
            try:
                stage_loading_phase.set_phase(PHASE_INITIALIZING, "Initializing simulation...")
            except Exception:
                pass

            # Step 1: enable simulation loop
            try:
                s = self._settings if self._settings else carb.settings.get_settings()
                s.set("/app/runLoops/mainLoop/simulationEnabled", True)
                print("[stage_core] ✓ Simulation enabled")
            except Exception as e:
                print(f"[stage_core] ⚠️ Could not set simulationEnabled: {e}")

            # Step 1.5: ensure terrain payloads loaded
            self._ensure_terrain_payloads_loaded()

            # Step 1.6: instancer settle — no SDK "instancers ready" event; wait up to N frames with progress
            try:
                stage_loading_phase.set_phase(
                    PHASE_INITIALIZING,
                    f"Initializing simulation (instanced geometry, up to {SETTLE_FRAMES_BEFORE_PLAYER} frames)...",
                )
            except Exception:
                pass
            print(f"[stage_core] ⏳ Waiting for instanced geometry (up to {SETTLE_FRAMES_BEFORE_PLAYER} frames)...")
            ok = await self._wait_frames_with_progress(
                SETTLE_FRAMES_BEFORE_PLAYER,
                PHASE_INITIALIZING,
                "Initializing simulation",
                gen,
            )
            if not ok:
                self._initialization_in_progress = False
                return

            # Step 2: start timeline
            import omni.timeline

            timeline = omni.timeline.get_timeline_interface()
            if not timeline:
                print("[stage_core] ❌ Timeline interface not available")
                self._initialization_in_progress = False
                return
            if not timeline.is_playing():
                timeline.play()
                await kit_app.get_app().next_update_async()

            if self._generation != gen:
                print("[stage_core] aborting stale initialization (generation changed after timeline)")
                self._initialization_in_progress = False
                return

            self._timeline_started = bool(timeline.is_playing())
            if not self._timeline_started:
                print("[stage_core] ❌ Timeline failed to start")
                self._initialization_in_progress = False
                return

            try:
                stage_readiness.mark_timeline_started()
            except Exception:
                pass

            # Step 3: wait one frame for physics to initialize
            await kit_app.get_app().next_update_async()

            if self._generation != gen:
                print("[stage_core] aborting stale initialization (generation changed after physics)")
                self._initialization_in_progress = False
                return

            # Signal PlayerCore via settings-backed gate
            try:
                stage_loading_phase.set_phase(PHASE_READY_FOR_PLAYER, "Preparing player...")
            except Exception:
                pass
            try:
                s = self._settings if self._settings else carb.settings.get_settings()
                s.set(self.READY_FOR_PLAYER_SETTING, True)
                print("[stage_core] ✓ readyForPlayer set (settings-backed)")
            except Exception as e:
                print(f"[stage_core] could not set readyForPlayer: {e}")

            self._initialization_complete = True
            self._initialization_in_progress = False
        except Exception as e:
            print(f"[stage_core] initialize_after_loading error: {e}")
            self._initialization_in_progress = False

