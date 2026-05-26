import time


class UiStageService:
    """
    Always-on UI/stage commands that must work even before appReady:
    - ui.ready: re-emit scene.loaded if already initialized
    - getChildrenRequest: stage tree browsing in the web UI

    Includes a lightweight streaming health monitor that logs diagnostics
    when the ui.ready frequency suggests a poisoned session.  No automatic
    restart is attempted — disabling livestream extensions cascades through
    the full dependency tree (messaging_core → all younite.*) and the
    recovery coroutine is cancelled by its own cascade, leaving the app
    permanently broken.
    """

    # ── streaming health-monitor tunables ────────────────────────────────
    _WD_THRESHOLD = 5
    _WD_WINDOW_SEC = 30.0

    def __init__(self, *, stage_manager, stage_readiness, track_task_cb=None, world_state=None):
        self._stage_manager = stage_manager
        self._stage_readiness = stage_readiness
        self._track_task = track_task_cb or (lambda t: t)
        self._world_state = world_state
        self._subs = []

        # health-monitor state
        self._wd_ui_ready_times: list = []
        self._wd_warned = False

    def start(self):
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler, order=0):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                try:
                    self._subs.append(
                        ed.observe_event(
                            observer_name=f"younite.usd_viewer_stage_core_extension/{name}",
                            event_name=name,
                            on_event=handler,
                            order=order,
                        )
                    )
                except Exception:
                    pass

            _observe("ui.ready", self._on_ui_ready)
            _observe("getChildrenRequest", self._on_get_children)
        except Exception:
            pass

    def stop(self):
        self._subs.clear()
        self._track_task = None
        self._stage_manager = None
        self._stage_readiness = None

    # ── core handlers ───────────────────────────────────────────────────

    def _on_ui_ready(self, _event):
        """Respond to client (re-request scene status / late connect): send current loading phase, then scene.loaded if ready."""
        try:
            import carb.eventdispatcher as _ed
            import omni.kit.app as kit_app
            import carb as _carb

            ed = _ed.get_eventdispatcher()

            # Mark client as connected so high-frequency outbound events are gated
            try:
                _carb.settings.get_settings().set("/younite/client/connected", True)
            except Exception:
                pass

            # Always send current loading phase so client shows correct step (e.g. connected during setup)
            try:
                from younite.usd_viewer_stage_core_extension.stage_loading_phase import stage_loading_phase
                phase = stage_loading_phase.get_phase()
                message = stage_loading_phase.get_message()
                payload = {"phase": phase, "message": message}
                kit_app.register_event_alias(
                    __import__("carb").events.type_from_string("loading.phase"), "loading.phase"
                )
                ed.dispatch_event("loading.phase", payload)
                print(f"[ui_stage] ui.ready received — dispatched loading.phase: {phase}")
            except Exception:
                pass

            # Streaming watchdog: track ui.ready frequency after initialization
            self._check_streaming_health()

            # If already initialized, send scene.loaded so client can leave loading overlay
            if not self._stage_readiness.is_initialized():
                print("[ui_stage] ui.ready received — stage not yet initialized, skipping scene.loaded")
                return
            import omni.usd as _omni_usd

            stage = _omni_usd.get_context().get_stage()
            scene_path = ""
            if stage:
                root = stage.GetRootLayer()
                scene_path = getattr(root, "identifier", "") or ""
            current_vt = str(_carb.settings.get_settings().get("/younite/camera/viewType") or "firstPerson")
            ed.dispatch_event("scene.loaded", {"scene": scene_path, "success": True, "viewType": current_vt})
            print(f"[ui_stage] ui.ready received — dispatched scene.loaded (viewType={current_vt})")

            if self._world_state:
                try:
                    self._world_state.push_snapshot()
                    print("[ui_stage] ui.ready — pushed worldStateSync snapshot")
                except Exception:
                    pass
        except Exception:
            pass

    def _on_get_children(self, event):
        try:
            if not self._stage_manager:
                return
            payload = getattr(event, "payload", None) or {}
            prim_path = payload.get("prim_path", "/")
            filters = payload.get("filters")
            children = self._stage_manager.get_children(prim_path=prim_path, filters=filters)
            import carb.eventdispatcher as _ed

            _ed.get_eventdispatcher().dispatch_event("getChildrenResponse", {"prim_path": prim_path, "children": children})
        except Exception:
            pass

    # ── streaming health monitor (diagnostic only) ─────────────────────
    #
    # Detects rapid ui.ready frequency that indicates a poisoned NVST
    # session (e.g. incompatible browser where the data channel partially
    # works but video never starts).
    #
    # Recovery is NOT attempted automatically: disabling livestream
    # extensions cascades through the Kit dependency tree (messaging_core
    # depends on livestream.app → all younite.* extensions shut down) and
    # the recovery coroutine is cancelled by its own cascade, leaving the
    # app permanently dead.  Manual Kit restart is the safe recovery path.

    def _check_streaming_health(self):
        """Called from _on_ui_ready.  Logs a warning if ui.ready frequency is abnormal."""
        if not self._stage_readiness.is_initialized():
            return

        now = time.monotonic()
        self._wd_ui_ready_times.append(now)
        cutoff = now - self._WD_WINDOW_SEC
        self._wd_ui_ready_times = [t for t in self._wd_ui_ready_times if t >= cutoff]

        count = len(self._wd_ui_ready_times)
        if count >= self._WD_THRESHOLD and not self._wd_warned:
            self._wd_warned = True
            print(
                f"[ui_stage] streaming health: {count} ui.ready in {self._WD_WINDOW_SEC}s "
                f"— possible poisoned NVST session. Restart Kit to recover."
            )

