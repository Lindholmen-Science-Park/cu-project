import omni.ext


class AiAgentExtension(omni.ext.IExt):
    """Thin extension entry-point for the AI agent chat service.

    Subscribes to ``ai.agent.request`` (Events 2.0) and delegates to
    :class:`AgentService`.  Also handles ``avatarPrim.hide`` /
    ``avatarPrim.show`` to toggle the NPC prim visibility when
    the chat overlay opens/closes.
    """

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._svc = None
        self._hidden_avatar_path = None

        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()

            # -- ai.agent.request -------------------------------------------------
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("ai.agent.request"),
                    "ai.agent.request",
                )
            except Exception:
                pass

            def _on_request(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                text = str(payload.get("text") or payload.get("message") or "")
                avatar_id = str(payload.get("avatarId") or payload.get("avatar_id") or "default")
                language = str(payload.get("language") or "").strip() or None

                # Resolve player geolocation (main thread — safe for USD queries)
                lat, lon = None, None
                try:
                    from younite.usd_viewer_player_core_extension import extension as _pc
                    _inst = getattr(_pc, "_instance", None)
                    pls = _inst.get_player_location_service() if _inst else None
                    if pls:
                        geo = pls.get_player_geo_position()
                        if geo:
                            lat, lon = round(geo[0], 6), round(geo[1], 6)
                            print(f"[ai_agent] player geolocation: lat={lat}, lon={lon}")
                except Exception:
                    pass

                if self._svc and text:
                    try:
                        self._svc.process_request(text, avatar_id, language=language, latitude=lat, longitude=lon)
                    except Exception as exc:
                        print(f"[ai_agent] process_request failed: {exc}")

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.ai_agent_extension/ai.agent.request",
                    event_name="ai.agent.request",
                    on_event=_on_request,
                    order=0,
                )
            )

            # -- ai.agent.setLanguage ----------------------------------------------
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("ai.agent.setLanguage"),
                    "ai.agent.setLanguage",
                )
            except Exception:
                pass

            def _on_set_language(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                lang = str(payload.get("language") or "").strip()
                if self._svc and lang:
                    self._svc.set_language(lang)

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.ai_agent_extension/ai.agent.setLanguage",
                    event_name="ai.agent.setLanguage",
                    on_event=_on_set_language,
                    order=0,
                )
            )

            # -- avatarPrim.hide / avatarPrim.show --------------------------------
            for evt_name in ("avatarPrim.hide", "avatarPrim.show"):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(evt_name), evt_name,
                    )
                except Exception:
                    pass

            def _on_avatar_hide(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                prim_path = str(payload.get("primPath") or "").strip()
                if prim_path:
                    self._set_avatar_visible(prim_path, False)

            def _on_avatar_show(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                prim_path = str(payload.get("primPath") or "").strip()
                if prim_path:
                    self._set_avatar_visible(prim_path, True)

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.ai_agent_extension/avatarPrim.hide",
                    event_name="avatarPrim.hide",
                    on_event=_on_avatar_hide,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.ai_agent_extension/avatarPrim.show",
                    event_name="avatarPrim.show",
                    on_event=_on_avatar_show,
                    order=0,
                )
            )

            # -- ui.ready: restore hidden avatar when a (new) client connects ------
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("ui.ready"), "ui.ready",
                )
            except Exception:
                pass

            def _on_ui_ready(_evt):
                if self._hidden_avatar_path:
                    print(f"[ai_agent] ui.ready — restoring hidden avatar: {self._hidden_avatar_path}")
                    self._set_avatar_visible(self._hidden_avatar_path, True)

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.ai_agent_extension/ui.ready",
                    event_name="ui.ready",
                    on_event=_on_ui_ready,
                    order=0,
                )
            )

            # -- WebRTC connect / disconnect (session grace timer) ----------------
            def _on_webrtc_connected(_evt):
                if self._svc:
                    self._svc.on_client_connected()

            def _on_webrtc_disconnected(_evt):
                if self._svc:
                    self._svc.on_client_disconnected()

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.ai_agent_extension/webrtc_connected",
                    event_name="omni.kit.livestream@connected",
                    on_event=_on_webrtc_connected,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.ai_agent_extension/webrtc_disconnected",
                    event_name="omni.kit.livestream@disconnected",
                    on_event=_on_webrtc_disconnected,
                    order=0,
                )
            )

        except Exception as exc:
            print(f"[ai_agent] subscribe failed: {exc}")

        try:
            from .agent_service import AgentService
            self._svc = AgentService()
        except Exception as exc:
            self._svc = None
            print(f"[ai_agent] AgentService init failed: {exc}")

    def _set_avatar_visible(self, prim_path: str, visible: bool):
        try:
            from younite.payload_orchestrator_core_extension import show_hide, Priority

            show_hide(prim_path, visible, Priority.HIGH, source="ai_agent_chat")
            self._hidden_avatar_path = None if visible else prim_path
        except Exception as exc:
            print(f"[ai_agent] avatar visibility failed: {exc}")

    def on_shutdown(self):
        if self._hidden_avatar_path:
            self._set_avatar_visible(self._hidden_avatar_path, True)
        if self._svc:
            try:
                self._svc.shutdown()
            except Exception:
                pass
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._svc = None
