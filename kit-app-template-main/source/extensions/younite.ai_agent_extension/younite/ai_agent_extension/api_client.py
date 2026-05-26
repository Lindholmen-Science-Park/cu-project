from __future__ import annotations

import base64
import json
import os
import urllib.request
import urllib.error
from typing import Optional

from .models import AgentResponse


class APIError(Exception):
    """Raised when the agent API call fails."""

    def __init__(self, message: str, error_type: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.error_type = error_type
        self.cause = cause


class APIClient:
    """HTTP client for the external AI agent API.

    Configuration via environment variables:

    * ``AI_AGENT_API_URL``  — chat endpoint (default: ``https://esbst.goteborg.se/citiverse/chat``)
    * ``AI_AGENT_USERNAME`` — HTTP Basic Auth username
    * ``AI_AGENT_PASSWORD`` — HTTP Basic Auth password
    * ``AI_AGENT_TIMEOUT``  — request timeout in seconds (default 30)

    Language is passed per-request by :class:`AgentService` (not stored
    here) so it can be changed at runtime.

    When credentials are missing the client reports itself as offline.
    """

    def __init__(self):
        self._api_url: str = os.getenv("AI_AGENT_API_URL", "https://esbst.goteborg.se/citiverse/chat")
        self._username: str = os.getenv("AI_AGENT_USERNAME", "")
        self._password: str = os.getenv("AI_AGENT_PASSWORD", "")
        self._timeout: int = int(os.getenv("AI_AGENT_TIMEOUT", "30"))
        self._configured = bool(self._api_url and self._username and self._password)

        if not self._configured:
            missing = []
            if not self._api_url:
                missing.append("AI_AGENT_API_URL")
            if not self._username:
                missing.append("AI_AGENT_USERNAME")
            if not self._password:
                missing.append("AI_AGENT_PASSWORD")
            print(f"[ai_agent] Missing env vars {', '.join(missing)} — AI agent is OFFLINE")
        else:
            print(f"[ai_agent] API client targeting {self._api_url} (user: {self._username})")

    @property
    def is_configured(self) -> bool:
        return self._configured

    def send_message(
        self,
        text: str,
        session_id: str,
        avatar_id: str,
        language: str = "en",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> AgentResponse:
        """Send a user message and return the parsed ``AgentResponse``.

        ``session_id`` and ``language`` are required by the API.

        Raises ``APIError`` on any failure so the caller can emit a
        user-friendly error event.
        """
        if not self._configured:
            raise APIError(
                "I'm currently offline. Please try again later.",
                error_type="offline",
            )
        return self._call_api(text, session_id, avatar_id, language, latitude, longitude)

    def close_session(self, session_id: str) -> None:
        """Tell the API to close a session. Best-effort, errors are swallowed."""
        if not self._configured or not session_id:
            return
        payload = {"action": "close_session", "session_id": session_id}
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": self._build_auth_header(),
        }
        req = urllib.request.Request(self._api_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as _:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_auth_header(self) -> str:
        credentials = f"{self._username}:{self._password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"

    def _call_api(
        self,
        text: str,
        session_id: str,
        avatar_id: str,
        language: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> AgentResponse:
        payload: dict = {
            "prompt": text,
            "session_id": session_id,
            "language": language,
        }
        if latitude is not None and longitude is not None:
            payload["latitude"] = latitude
            payload["longitude"] = longitude
        body = json.dumps(payload).encode("utf-8")

        print(f"[ai_agent] POST {self._api_url}")
        print(f"[ai_agent] Sending: {json.dumps(payload)}")

        headers = {
            "Content-Type": "application/json",
            "Authorization": self._build_auth_header(),
        }

        req = urllib.request.Request(
            self._api_url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                print(f"[ai_agent] Response {resp.status}: {raw[:500]}")
        except urllib.error.HTTPError as exc:
            status = exc.code
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="ignore")[:500]
            except Exception:
                pass
            print(f"[ai_agent] HTTP {status}: {detail}")
            raise APIError(
                "Something went wrong on my end. Please try again later.",
                error_type="http_error",
                cause=exc,
            )
        except urllib.error.URLError as exc:
            print(f"[ai_agent] URLError: {exc.reason}")
            raise APIError(
                "I'm having trouble connecting right now. Please try again in a moment.",
                error_type="connection_error",
                cause=exc,
            )
        except TimeoutError as exc:
            print(f"[ai_agent] Timeout after {self._timeout}s")
            raise APIError(
                "The response is taking too long. Please try again.",
                error_type="timeout",
                cause=exc,
            )
        except OSError as exc:
            print(f"[ai_agent] OSError: {exc}")
            raise APIError(
                "I'm having trouble connecting right now. Please try again in a moment.",
                error_type="connection_error",
                cause=exc,
            )

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise APIError(
                "I received an unexpected response. Please try again.",
                error_type="parse_error",
                cause=exc,
            )

        try:
            return AgentResponse.from_dict(data)
        except Exception as exc:
            raise APIError(
                "I received an unexpected response. Please try again.",
                error_type="parse_error",
                cause=exc,
            )
