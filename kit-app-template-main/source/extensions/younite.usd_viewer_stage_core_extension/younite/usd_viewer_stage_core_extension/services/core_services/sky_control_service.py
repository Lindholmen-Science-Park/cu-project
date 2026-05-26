class SkyControlService:
    """Forwards skyControlRequest to stage manager. Always tries to apply; retries on no_env/no_light (Environment/reference may load late)."""

    MAX_RETRIES = 5
    RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 15.0)

    def __init__(self, *, stage_manager, stage_readiness, track_task_cb, world_state=None):
        self._stage_manager = stage_manager
        self._stage_readiness = stage_readiness
        self._track_task = track_task_cb or (lambda t: t)
        self._world_state = world_state
        self._subs = []

    def start(self):
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
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
                            observer_name=f"younite.usd_viewer_stage_core_extension/{name}",
                            event_name=name,
                            on_event=handler,
                            order=0,
                        )
                    )
                except Exception:
                    pass

            _observe("skyControlRequest", self._on_sky_control)
        except Exception:
            pass

    def stop(self):
        self._subs.clear()
        self._track_task = None
        self._stage_manager = None

    def _apply_with_retry(self, payload, retry_index=0):
        """Apply sky control; if no_env or no_light, schedule a retry (Environment/lights may load late)."""
        try:
            class _Evt:
                def __init__(self, p):
                    self.payload = p
            result = self._stage_manager._on_sky_control(_Evt(payload))
            if result in ("no_env", "no_light") and retry_index < self.MAX_RETRIES:
                delay = self.RETRY_DELAYS[retry_index]
                print(f"[sky_control] {result} — retrying in {delay}s (attempt {retry_index + 1}/{self.MAX_RETRIES})")
                import asyncio
                async def _retry():
                    await asyncio.sleep(delay)
                    self._apply_with_retry(payload, retry_index + 1)
                try:
                    self._track_task(asyncio.ensure_future(_retry()))
                except Exception:
                    pass
            elif result in ("no_env", "no_light"):
                print(f"[sky_control] {result} — all {self.MAX_RETRIES} retries exhausted")
            elif result == "ok":
                self._publish_resolved_state(payload)
        except Exception:
            pass

    def _publish_resolved_state(self, payload):
        """Push resolved applied sky state to the world state registry."""
        if not self._world_state:
            return
        try:
            from younite.weather_and_seasons_extension.sky_service import WEATHER_PRESETS

            updates = {}
            if "timeOfDay" in payload:
                try:
                    updates["timeOfDay"] = float(payload["timeOfDay"])
                except (TypeError, ValueError):
                    pass
            if "dayOfYear" in payload:
                try:
                    updates["dayOfYear"] = int(float(payload["dayOfYear"]))
                except (TypeError, ValueError):
                    pass
            if "cloudCoverage" in payload:
                try:
                    updates["cloudCoverage"] = float(payload["cloudCoverage"])
                except (TypeError, ValueError):
                    pass
            if "cumulusEnabled" in payload:
                updates["cumulusEnabled"] = bool(payload["cumulusEnabled"])

            if "weatherPreset" in payload:
                preset_key = str(payload["weatherPreset"])
                updates["weatherPreset"] = preset_key
                preset = WEATHER_PRESETS.get(preset_key)
                if preset:
                    updates["cloudCoverage"] = preset["cloud_coverage"] + 0.5
                    updates["cumulusEnabled"] = preset["cumulus"]
                    rain = preset.get("rain", 0.0)
                    fog = preset.get("fog", 0.0)
                    updates["fogEnabled"] = fog > 0
                    updates["fogIntensity"] = fog

            if updates:
                self._world_state.set_many(updates)
        except Exception:
            pass

    def _on_sky_control(self, event):
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload
            raw_payload = getattr(event, "payload", None)
            if raw_payload is None and isinstance(event, (tuple, list)) and len(event) > 0 and isinstance(event[0], dict):
                raw_payload = event[0]
            elif raw_payload is None and isinstance(event, dict):
                raw_payload = event
            raw_payload = raw_payload or {}
            payload = normalize_event_payload(raw_payload)
            if not isinstance(payload, dict):
                return
            # Always try to apply (no is_stage_ready gate); retry if Environment/lights not ready yet
            self._apply_with_retry(payload, 0)
        except Exception:
            pass
