from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


class ActionHandlerService:
    """
    Action handler service:
    - iterates actions list
    - routes by target (3d/web)
    - provides built-in debug actions
    """

    def __init__(self, *, dispatch_event, emit_web_event):
        # dispatch_event(name: str, payload: dict) -> None
        # emit_web_event(name: str, payload: dict) -> None  (implemented as dispatch_event too, but kept explicit)
        self._dispatch_event = dispatch_event
        self._emit_web_event = emit_web_event

    def execute_onclick(self, *, interactable_id: str, actions: Iterable[dict]) -> None:
        for a in list(actions or []):
            if not isinstance(a, dict):
                continue
            target = str(a.get("target") or "").strip().lower()
            action_name = str(a.get("action") or "").strip()
            params = a.get("params") if isinstance(a.get("params"), dict) else {}
            payload = a.get("payload") if isinstance(a.get("payload"), dict) else {}

            if not target or not action_name:
                continue

            if target == "3d":
                self._run_3d_action(interactable_id=interactable_id, action=action_name, params=params)
            elif target == "web":
                self._run_web_action(interactable_id=interactable_id, action=action_name, payload=payload)

    def _run_3d_action(self, *, interactable_id: str, action: str, params: Dict[str, Any]) -> None:
        if action == "debug.print":
            msg = str(params.get("message") or f"{interactable_id} clicked")
            try:
                print(msg)
            except Exception:
                pass
            return

        # Forward all other 3D actions to Kit-side listeners
        try:
            self._dispatch_event(
                "younite.interaction.action",
                {"interactableId": interactable_id, "action": action, "params": dict(params or {})},
            )
        except Exception:
            pass

    def _run_web_action(self, *, interactable_id: str, action: str, payload: Dict[str, Any]) -> None:
        try:
            self._emit_web_event(
                "interactionTriggered",
                {"interactableId": interactable_id, "action": action, "payload": dict(payload or {})},
            )
        except Exception:
            pass

