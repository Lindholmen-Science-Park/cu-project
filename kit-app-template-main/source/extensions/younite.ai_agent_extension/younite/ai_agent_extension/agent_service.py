from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

import carb
import carb.eventdispatcher

from .api_client import APIClient, APIError
from .models import AgentResponse
from .session_manager import SessionManager


class AgentService:
    """Orchestrates the avatar-chat request lifecycle.

    1. Emit ``ai.agent.typing``
    2. Call the external API on a background thread
    3. On success  -> ``ai.agent.response`` + ``ai.agent.done``
       On failure  -> ``ai.agent.error``   + ``ai.agent.done``

    Language is configurable at runtime via ``set_language()`` or by
    including a ``language`` field in the ``ai.agent.request`` payload.
    """

    def __init__(self):
        self._ed = carb.eventdispatcher.get_eventdispatcher()
        self._api = APIClient()
        self._sessions = SessionManager()
        self._language: str = os.getenv("AI_AGENT_LANGUAGE", "en")
        self._disconnect_grace_s: float = float(os.getenv("AI_AGENT_DISCONNECT_GRACE", "300"))
        self._grace_timer: Optional[threading.Timer] = None

        status = "ONLINE" if self._api.is_configured else "OFFLINE (missing credentials)"
        print(f"[ai_agent] AgentService ready — {status} (lang: {self._language}, grace: {self._disconnect_grace_s}s)")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, lang: str) -> None:
        """Change the language used for subsequent API requests."""
        lang = (lang or "").strip().lower()
        if lang and lang != self._language:
            self._language = lang

    def process_request(
        self,
        text: str,
        avatar_id: str,
        language: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> None:
        """Handle an inbound chat message — called from the extension.

        If *language* is provided it becomes the new default for all
        future requests (sticky change).
        """
        text = (text or "").strip()
        if not text:
            return

        if language:
            self.set_language(language)

        session_id = self._sessions.get_or_create_session(avatar_id)

        self._emit("ai.agent.typing", {
            "avatarId": avatar_id,
            "sessionId": session_id,
        })

        thread = threading.Thread(
            target=self._background_call,
            args=(text, session_id, avatar_id, self._language, latitude, longitude),
            daemon=True,
        )
        thread.start()

    def on_client_disconnected(self) -> None:
        """Start the grace timer — sessions are closed if no reconnect."""
        self._cancel_grace_timer()
        if not self._sessions.all_session_ids():
            return
        self._grace_timer = threading.Timer(
            self._disconnect_grace_s, self._on_grace_expired,
        )
        self._grace_timer.daemon = True
        self._grace_timer.start()
        print(f"[ai_agent] client disconnected — grace timer started ({self._disconnect_grace_s}s)")

    def on_client_connected(self) -> None:
        """Cancel any pending grace timer — client is back."""
        if self._grace_timer is not None:
            self._cancel_grace_timer()
            print("[ai_agent] client reconnected — grace timer cancelled, sessions preserved")

    def shutdown(self) -> None:
        """Best-effort close of all active sessions on the API side."""
        self._cancel_grace_timer()
        self._close_all_sessions()

    # ------------------------------------------------------------------
    # Grace timer internals
    # ------------------------------------------------------------------

    def _cancel_grace_timer(self) -> None:
        if self._grace_timer is not None:
            self._grace_timer.cancel()
            self._grace_timer = None

    def _on_grace_expired(self) -> None:
        print("[ai_agent] grace period expired — closing all sessions")
        self._grace_timer = None
        self._close_all_sessions()

    def _close_all_sessions(self) -> None:
        for sid in self._sessions.all_session_ids():
            self._api.close_session(sid)
        self._sessions.clear_all()

    # ------------------------------------------------------------------
    # Background work
    # ------------------------------------------------------------------

    def _background_call(
        self,
        text: str,
        session_id: str,
        avatar_id: str,
        language: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> None:
        try:
            response: AgentResponse = self._api.send_message(
                text, session_id, avatar_id, language,
                latitude=latitude, longitude=longitude,
            )

            # If the API reassigned a different session ID, update our mapping
            if response.session_id and response.session_id != session_id:
                self._sessions.set_session(avatar_id, response.session_id)
                session_id = response.session_id

            payload = response.to_event_payload(avatar_id, session_id, language=language)
            self._emit("ai.agent.response", payload)

        except APIError as exc:
            # NOTE: APIError messages in api_client.py are hardcoded English,
            # so we deliberately do NOT echo `language` here — letting the
            # frontend fall back to its own UI-localized error string (or use
            # the UI language for the spoken voice).
            self._emit("ai.agent.error", {
                "avatarId": avatar_id,
                "sessionId": session_id,
                "text": str(exc),
                "errorType": exc.error_type,
            })

        except Exception as exc:
            self._emit("ai.agent.error", {
                "avatarId": avatar_id,
                "sessionId": session_id,
                "text": "Something unexpected happened. Please try again.",
                "errorType": "unknown",
            })

        finally:
            self._emit("ai.agent.done", {
                "avatarId": avatar_id,
                "sessionId": session_id,
            })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        try:
            import omni.kit.app as _kit_app
            _kit_app.register_event_alias(
                carb.events.type_from_string(event_name), event_name,
            )
        except Exception:
            pass
        try:
            self._ed.dispatch_event(event_name, payload)
        except Exception as exc:
            print(f"[ai_agent] emit failed for {event_name}: {exc}")
