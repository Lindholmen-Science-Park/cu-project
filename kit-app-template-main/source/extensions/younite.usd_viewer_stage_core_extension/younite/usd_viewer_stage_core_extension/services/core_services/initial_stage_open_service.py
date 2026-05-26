import asyncio


class InitialStageOpenService:
    """
    Owns opening the initial stage configured via `/app/auto_load_usd`.

    This used to be in SetupExtension; StageCore owns stage lifecycle end-to-end.
    """

    def __init__(
        self,
        *,
        settings,
        auto_load_usd_setting: str,
        warmup_mode_setting: str,
        empty_stage_on_start_setting: str,
        command_macro_file_setting: str,
        track_task_cb,
        frame_delay: int = 6,
    ):
        self._settings = settings
        self._auto_load_usd_setting = auto_load_usd_setting
        self._warmup_mode_setting = warmup_mode_setting
        self._empty_stage_on_start_setting = empty_stage_on_start_setting
        self._command_macro_file_setting = command_macro_file_setting
        self._track_task = track_task_cb or (lambda t: t)
        self._frame_delay = int(frame_delay)

        self._task = None

    def start(self):
        try:
            self._task = self._track_task(asyncio.ensure_future(self._open_initial_stage_if_configured()))
        except Exception:
            self._task = None

    def stop(self):
        try:
            if self._task is not None and hasattr(self._task, "cancel"):
                self._task.cancel()
        except Exception:
            pass
        self._task = None
        self._track_task = None

    async def _open_initial_stage_if_configured(self):
        try:
            s = self._settings
            if s and bool(s.get(self._warmup_mode_setting)):
                return

            # If benchmark macro is set, do not auto-load a stage
            try:
                if s and s.get(self._command_macro_file_setting):
                    return
            except Exception:
                pass

            stage_url = ""
            try:
                if s:
                    stage_url = s.get_as_string(self._auto_load_usd_setting) or ""
            except Exception:
                stage_url = ""

            if not stage_url:
                return

            # Resolve tokens
            try:
                import carb.tokens

                stage_url = carb.tokens.get_tokens_interface().resolve(stage_url) or stage_url
            except Exception:
                pass

            # Ensure absolute path to avoid bad relative reference resolution
            try:
                from pathlib import Path

                p = Path(stage_url)
                if not p.is_absolute():
                    stage_url = str(p.resolve())
            except Exception:
                pass

            # Wait for UI/layout bootstrap
            try:
                import omni.kit.app as kit_app

                app = kit_app.get_app()
                for _ in range(int(max(0, self._frame_delay))):
                    await app.next_update_async()
            except Exception:
                pass

            import omni.usd

            ctx = omni.usd.get_context()
            # Avoid double-open if something else already opened a stage
            try:
                stage = ctx.get_stage()
                if stage:
                    root = stage.GetRootLayer()
                    if getattr(root, "identifier", ""):
                        return
            except Exception:
                pass

            # Tell UI we are starting to load (even if UI isn't connected yet)
            try:
                import carb.eventdispatcher as _ed

                _ed.get_eventdispatcher().dispatch_event("scene.loading", {"target": stage_url})
            except Exception:
                pass

            try:
                from younite.usd_viewer_stage_core_extension.stage_loading_phase import (
                    stage_loading_phase,
                    PHASE_OPENING_STAGE,
                )
                stage_loading_phase.set_phase(PHASE_OPENING_STAGE, "Opening scene...")
            except Exception:
                pass

            print(f"[stage_core] opening initial stage: {stage_url}")

            try:
                result = await ctx.open_stage_async(stage_url, omni.usd.UsdContextInitialLoadSet.LOAD_ALL)
                # Some builds return (success, error); ignore either way.
                if isinstance(result, tuple) and len(result) == 2:
                    _success, _err = result
            except Exception as e:
                print(f"[stage_core] ❌ initial stage open failed: {e}")
                return

            # Restore render settings, matching old SetupExtension behavior
            try:
                if not bool(s.get(self._empty_stage_on_start_setting) if s else False):
                    ctx.load_render_settings_from_stage(ctx.get_stage_id())
            except Exception:
                pass
        except Exception as e:
            print(f"[stage_core] initial stage open task failed: {e}")

