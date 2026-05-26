import carb


class StageReadiness:
    def __init__(self) -> None:
        self._opened = False
        self._assets_loaded = False
        self._timeline_started = False
        self._initialized = False
        try:
            import carb.settings
            self._settings = carb.settings.get_settings()
        except Exception:
            self._settings = None

    # --- Setters updated by the Extension ---
    def mark_opened(self) -> None:
        self._opened = True
        self._emit_settings()

    def mark_assets_loaded(self) -> None:
        self._assets_loaded = True
        self._emit_settings()

    def mark_timeline_started(self) -> None:
        self._timeline_started = True
        self._emit_settings()

    def mark_initialized(self) -> None:
        self._initialized = True
        self._emit_settings()
        self._dispatch_event("stageReady")

    def mark_closed(self) -> None:
        self._opened = False
        self._assets_loaded = False
        self._timeline_started = False
        self._initialized = False
        self._emit_settings()
        self._dispatch_event("stageClosed")

    # --- Consumer API ---
    def is_stage_ready(self) -> bool:
        return self._opened and self._assets_loaded and self._initialized

    def is_initialized(self) -> bool:
        return bool(self._initialized)

    def status(self) -> dict:
        return {
            "opened": self._opened,
            "assetsLoaded": self._assets_loaded,
            "timelineStarted": self._timeline_started,
            "initialized": self._initialized,
            "ready": self.is_stage_ready(),
        }

    # --- Internals ---
    def _dispatch_event(self, event_name: str) -> None:
        try:
            ed = carb.eventdispatcher.get_eventdispatcher()
            ed.dispatch_event(event_name, payload=self.status())
        except Exception:
            pass

    def _emit_settings(self) -> None:
        try:
            s = self._settings if self._settings else carb.settings.get_settings()
            s.set("/younite/stage/opened", self._opened)
            s.set("/younite/stage/assetsLoaded", self._assets_loaded)
            s.set("/younite/stage/timelineStarted", self._timeline_started)
            s.set("/younite/stage/initialized", self._initialized)
            s.set("/younite/stage/ready", self.is_stage_ready())
        except Exception:
            pass


stage_readiness = StageReadiness()

