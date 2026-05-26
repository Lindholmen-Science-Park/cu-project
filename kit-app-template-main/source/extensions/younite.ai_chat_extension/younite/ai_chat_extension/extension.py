import omni.ext


class AiChatExtension(omni.ext.IExt):
    """AI chat feature using the real `AIService` port."""

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._svc = None

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()
            try:
                kit_app.register_event_alias(carb.events.type_from_string("ai.chat.request"), "ai.chat.request")
            except Exception:
                pass

            def _on_chat(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                text = str(payload.get("text") or payload.get("message") or "")
                session_id = str(payload.get("sessionId") or payload.get("session_id") or "default")
                try:
                    if self._svc:
                        self._svc.process_chat_request(text, session_id)
                except Exception:
                    pass

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.ai_chat_extension/ai.chat.request",
                    event_name="ai.chat.request",
                    on_event=_on_chat,
                    order=0,
                )
            )
        except Exception as e:
            print(f"[ai_chat] subscribe failed: {e}")

        # Create service after subscriptions so it can emit events immediately
        try:
            from .ai_service import AIService
            self._svc = AIService()
        except Exception as e:
            self._svc = None
            print(f"[ai_chat] AIService init failed: {e}")

    def on_shutdown(self):
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._svc = None

