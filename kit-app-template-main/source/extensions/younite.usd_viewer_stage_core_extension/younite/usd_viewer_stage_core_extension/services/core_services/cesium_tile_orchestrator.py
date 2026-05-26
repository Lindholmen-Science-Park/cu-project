"""
Cesium tile-streaming orchestrator — controls how often tiles update
based on the active camera view mode.

Modes
-----
- **Bird's eye**: Periodic "pulse" updates. Tiles are suspended most of
  the time, but every ``UPDATE_INTERVAL_SECONDS`` the orchestrator
  unsuspends for ``UPDATE_BURST_FRAMES`` frames so the Cesium runtime
  can process pending tile requests.  This keeps the terrain visually
  current without burning CPU/GPU every single frame.

- **First person**: Tiles are fully suspended (``suspendUpdate = true``).
  The player is on the ground and terrain detail rarely matters enough
  to justify the per-frame cost.

- **Initial load**: On ``scene.loaded`` the orchestrator waits
  ``INITIAL_LOAD_SECONDS`` with tiles *un*suspended so the first batch
  of terrain can stream in, then switches to the mode that matches the
  current view type.
"""

import asyncio

import omni.kit.app as kit_app


class CesiumTileOrchestrator:

    INITIAL_LOAD_SECONDS = 12.0
    UPDATE_INTERVAL_SECONDS = 1.0
    UPDATE_BURST_FRAMES = 10

    def __init__(self, *, track_task_cb=None):
        self._track_task = track_task_cb or (lambda t: t)
        self._subs = []
        self._pulse_task = None
        self._init_task = None
        self._active_mode = None
        self._scene_loaded = False
        self._token_applied = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        try:
            import carb.eventdispatcher
            import carb.events
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                try:
                    self._subs.append(
                        ed.observe_event(
                            observer_name=f"younite.cesium_tile_orchestrator/{name}",
                            event_name=name,
                            on_event=handler,
                            order=0,
                        )
                    )
                except Exception:
                    pass

            _observe("younite.camera.viewTypeChanged", self._on_view_type_changed)
            _observe("scene.loaded", self._on_scene_loaded)
            _observe("omni.usd@stage_event", self._on_stage_event)
        except Exception as e:
            print(f"[cesium_orchestrator] start failed: {e}")

    def stop(self):
        self._cancel_tasks()
        self._subs.clear()
        self._track_task = None
        self._active_mode = None
        self._scene_loaded = False
        self._token_applied = False

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_stage_event(self, event):
        if self._token_applied:
            return
        try:
            et = int(getattr(event, "type", -1))
            from omni.usd import StageEventType
            if et == int(StageEventType.OPENED):
                self._apply_cesium_ion_token()
        except Exception:
            pass

    def _apply_cesium_ion_token(self):
        """Override Cesium Ion access token from CESIUM_ION_TOKEN env var
        onto the session layer, so the token lives only in .env."""
        import os
        token = os.environ.get("CESIUM_ION_TOKEN", "")
        if not token:
            return
        try:
            import omni.usd
            from pxr import Sdf, Usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            prim = stage.GetPrimAtPath("/CesiumServers/IonOfficial")
            if not prim or not prim.IsValid():
                return

            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                attr = prim.GetAttribute("cesium:projectDefaultIonAccessToken")
                if attr and attr.IsValid():
                    attr.Set(token)

            self._token_applied = True
            print(f"[cesium_orchestrator] Ion token applied from env ({len(token)} chars)")
        except Exception as e:
            print(f"[cesium_orchestrator] token override failed: {e}")

    def _on_scene_loaded(self, event):
        if self._scene_loaded:
            return
        self._scene_loaded = True
        self._cancel_tasks()
        self._init_task = self._track_task(
            asyncio.ensure_future(self._initial_load_then_activate())
        )

    def _on_view_type_changed(self, event):
        if not self._scene_loaded:
            return
        payload = getattr(event, "payload", None) or {}
        view_type = payload.get("viewType", "firstPerson")
        self._activate_mode(view_type)

    # ------------------------------------------------------------------
    # Mode control
    # ------------------------------------------------------------------

    def _activate_mode(self, view_type: str):
        self._cancel_pulse()
        if view_type == "birdEye":
            self._active_mode = "birdEye"
            self._set_suspend(False)
            print("[cesium_orchestrator] mode → birdEye (unsuspended)")
        else:
            self._active_mode = "firstPerson"
            self._set_suspend(True)
            print("[cesium_orchestrator] mode → firstPerson (frozen)")

    async def _initial_load_then_activate(self):
        """Let tiles stream during initial load, then enter the right mode."""
        try:
            self._set_suspend(False)
            print(
                f"[cesium_orchestrator] initial load — "
                f"tiles unsuspended for {self.INITIAL_LOAD_SECONDS}s"
            )
            await asyncio.sleep(self.INITIAL_LOAD_SECONDS)

            view_type = self._current_view_type()
            self._activate_mode(view_type)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[cesium_orchestrator] initial load error: {e}")
            self._set_suspend(True)

    async def _run_bird_eye_loop(self):
        """Periodically unsuspend tiles for a burst of frames."""
        app = kit_app.get_app()
        try:
            while True:
                self._set_suspend(False)
                for _ in range(self.UPDATE_BURST_FRAMES):
                    await app.next_update_async()
                self._set_suspend(True)
                await asyncio.sleep(self.UPDATE_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[cesium_orchestrator] pulse loop error: {e}")

    # ------------------------------------------------------------------
    # USD helpers
    # ------------------------------------------------------------------

    def _set_suspend(self, suspended: bool):
        try:
            import omni.usd
            from pxr import Sdf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            for prim in stage.Traverse():
                if prim.GetTypeName() == "CesiumTilesetPrim":
                    attr = prim.GetAttribute("cesium:suspendUpdate")
                    if attr and attr.IsValid():
                        attr.Set(suspended)
                    else:
                        prim.CreateAttribute(
                            "cesium:suspendUpdate", Sdf.ValueTypeNames.Bool
                        ).Set(suspended)
        except Exception as e:
            print(f"[cesium_orchestrator] set_suspend({suspended}) error: {e}")

    def _current_view_type(self) -> str:
        try:
            import carb.settings
            vt = carb.settings.get_settings().get("/younite/camera/viewType")
            return str(vt) if vt else "firstPerson"
        except Exception:
            return "firstPerson"

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def _cancel_pulse(self):
        if self._pulse_task and not self._pulse_task.done():
            self._pulse_task.cancel()
        self._pulse_task = None

    def _cancel_tasks(self):
        self._cancel_pulse()
        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
        self._init_task = None
