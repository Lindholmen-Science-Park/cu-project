from __future__ import annotations

import uuid
from typing import Dict, List, Optional


class SessionManager:
    """Tracks per-avatar session IDs.

    The external API expects the client to provide a ``session_id`` with
    every request.  On the first message for a given avatar, the manager
    generates a UUID and keeps it for subsequent messages.  If the API
    reassigns a different ``session_id`` in its response, call
    ``set_session()`` to update the mapping.
    """

    def __init__(self):
        self._avatar_to_session: Dict[str, str] = {}
        self._session_to_avatar: Dict[str, str] = {}

    def get_or_create_session(self, avatar_id: str) -> str:
        """Return the existing session ID or create a new one."""
        existing = self._avatar_to_session.get(avatar_id)
        if existing:
            return existing
        new_id = str(uuid.uuid4())
        self._avatar_to_session[avatar_id] = new_id
        self._session_to_avatar[new_id] = avatar_id
        return new_id

    def get_session(self, avatar_id: str) -> Optional[str]:
        """Return the stored session ID for *avatar_id*, or ``None``."""
        return self._avatar_to_session.get(avatar_id)

    def set_session(self, avatar_id: str, session_id: str) -> None:
        """Store or update the *session_id* for *avatar_id*."""
        old = self._avatar_to_session.get(avatar_id)
        if old:
            self._session_to_avatar.pop(old, None)
        self._avatar_to_session[avatar_id] = session_id
        self._session_to_avatar[session_id] = avatar_id

    def reset_session(self, avatar_id: str) -> None:
        """Discard the current session for *avatar_id*."""
        old = self._avatar_to_session.pop(avatar_id, None)
        if old:
            self._session_to_avatar.pop(old, None)

    def all_session_ids(self) -> List[str]:
        """Return all active session IDs (for bulk close on shutdown)."""
        return list(self._session_to_avatar.keys())

    def clear_all(self) -> None:
        """Discard all sessions (after bulk close on the API side)."""
        self._avatar_to_session.clear()
        self._session_to_avatar.clear()

    def get_avatar_id_for_session(self, session_id: str) -> Optional[str]:
        """Reverse lookup: session -> avatar."""
        return self._session_to_avatar.get(session_id)
