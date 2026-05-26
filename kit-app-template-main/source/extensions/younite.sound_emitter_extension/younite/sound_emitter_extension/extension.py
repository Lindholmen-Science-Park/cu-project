import omni.ext


class SoundEmitterExtension(omni.ext.IExt):
    """Publishes the ambient sound emitter list to the browser.

    - Loads ``source/data/sound_emitters.json`` and resolves each
      entry's world position from a matching empty Xform under ``/World``
      (recursive lookup by ``id == leaf name``).
    - Dispatches ``soundEmittersStatus`` on ``omni.usd@stage_event`` (OPENED)
      and ``younite.player.ready``; world-state sync observes that and folds
      ``soundEmitters`` into the ``worldStateSync`` snapshot.
    - Safe to run with an empty / missing JSON file or no matching prims:
      the emitter list is published as ``[]`` and the browser-side engine
      stays idle.
    - Re-publishes on request via ``soundEmitters.request`` so the ambient
      engine can force a refresh after editing the JSON.

    All ``from pxr import …`` statements live inside helper functions (see
    ``emitter_service``) to avoid module-level USD import failures.
    """

    EVENT_PUBLISH = "soundEmittersStatus"
    EVENT_REQUEST = "soundEmitters.request"

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._last_payload_count: int = -1

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

            def _observe(name: str, handler):
                _alias(name)
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.sound_emitter_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            _observe("omni.usd@stage_event", self._on_stage_event)
            _observe("younite.player.ready", self._on_player_ready)
            _observe(self.EVENT_REQUEST, self._on_request)

            print("[sound_emitter] extension started")
        except Exception as e:
            print(f"[sound_emitter] startup failed: {e}")

    def on_shutdown(self):
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()

    # ── internal ─────────────────────────────────────────────────────

    def _publish(self, reason: str) -> None:
        try:
            from .emitter_service import collect_sound_emitters, get_current_stage
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            stage = get_current_stage()
            emitters = collect_sound_emitters(stage)
            dispatch_to_events2(self.EVENT_PUBLISH, {"emitters": emitters})

            count = len(emitters)
            if count != self._last_payload_count:
                self._last_payload_count = count
                print(f"[sound_emitter] published {count} emitter(s) (reason={reason})")
        except Exception as e:
            print(f"[sound_emitter] publish failed: {e}")

    def _on_stage_event(self, event) -> None:
        try:
            from omni.usd import StageEventType
            et = int(getattr(event, "type", 0))
            if et == int(StageEventType.OPENED):
                self._publish("stage.opened")
        except Exception:
            pass

    def _on_player_ready(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload
            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            if bool(payload.get("success", True)):
                self._publish("player.ready")
        except Exception:
            pass

    def _on_request(self, _event) -> None:
        self._publish("request")
