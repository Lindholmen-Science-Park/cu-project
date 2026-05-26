"""
Centralised world-state registry.

Holds a flat dict of the last-known world settings and pushes the full
snapshot to web clients via the ``worldStateSync`` outbound event whenever
a value changes or when a client (re-)connects (``ui.ready``).

Stage-core services update the dict directly via ``set`` / ``set_many``.
External extensions (PeopleToggleExtension, NavMeshRouteExtension) are
observed through their existing outbound events so they need no changes.
"""
from __future__ import annotations

from typing import Optional


_DEFAULTS = {
    "timeOfDay": 12.0,
    "dayOfYear": 187,
    "cumulusEnabled": True,
    "cloudCoverage": 0.0,
    # weatherPreset is omitted until explicitly set — Kit startup applies
    # individual sky parameters, not a named preset.
    # First-person camera Y (cm): 1.70 m character − 15 cm eye offset = 155 — matches web CU default.
    "cameraHeight": 155,
    "movementSpeed": 1.0,
    "cameraViewType": "firstPerson",
    "fogEnabled": False,
    "fogIntensity": 0.0,
    "physicsState": "disabled",
    "peopleVisible": False,
    "navmeshMode": "walking",
    "navmeshBaking": False,
    "season": "summer",
    # Ambient sound emitters — populated by younite.sound_emitter_extension,
    # which loads source/data/sound_emitters.json and resolves each
    # entry's world position from a matching empty Xform under /World.
    # Empty by default so the browser-side ambient engine stays dormant
    # until JSON entries (and their matching Xforms) are authored.
    "soundEmitters": [],
    # Media packs: ``iconGroup`` templates may set ``contentThemes`` so only
    # the active pack's 360° / spatial-sound icons expand (see interactions).
    "mediaContentTheme": "horseshow",
    # Dev / CU: show red stair overlay (dual NavMesh diff); default off.
    "accessibilityDiffOverlayVisible": False,
    # Dev: translucent cyan mesh of the active NavMesh; default off.
    "navmeshDebugOverlayVisible": False,
}


class WorldStateSyncService:
    """Flat key-value store for world settings, pushed to web on change."""

    def __init__(self):
        self._state: dict = dict(_DEFAULTS)
        self._subs: list = []

    # ── public API (called by stage-core services) ───────────────────

    def set(self, key: str, value) -> None:
        """Update one key and push the full snapshot."""
        self._state[key] = value
        self._dispatch()

    def set_many(self, mapping: dict) -> None:
        """Update several keys in a single dispatch."""
        self._state.update(mapping)
        self._dispatch()

    def push_snapshot(self) -> None:
        """Re-dispatch the current snapshot without mutating it."""
        self._dispatch()

    def get_all(self) -> dict:
        return dict(self._state)

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(name), name
                    )
                except Exception:
                    pass
                try:
                    self._subs.append(
                        ed.observe_event(
                            observer_name=f"younite.world_state_sync/{name}",
                            event_name=name,
                            on_event=handler,
                            order=100,
                        )
                    )
                except Exception:
                    pass

            _observe("worldStateSync.request", self._on_sync_request)
            _observe("peopleToggleStatus", self._on_people_toggle_status)
            _observe("navmeshModeStatus", self._on_navmesh_mode_status)
            _observe("seasonStatus", self._on_season_status)
            _observe("soundEmittersStatus", self._on_sound_emitters_status)

        except Exception:
            pass

    def stop(self) -> None:
        self._subs.clear()

    # ── internal ─────────────────────────────────────────────────────

    def _dispatch(self) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            dispatch_to_events2("worldStateSync", dict(self._state))
        except Exception:
            pass

    def _on_sync_request(self, _event) -> None:
        self.push_snapshot()

    def _on_people_toggle_status(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(
                getattr(event, "payload", None) or {}
            )
            if "enabled" in payload:
                self._state["peopleVisible"] = bool(payload["enabled"])
        except Exception:
            pass

    def _on_season_status(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(
                getattr(event, "payload", None) or {}
            )
            season = payload.get("season")
            if season:
                self._state["season"] = str(season)
                self._dispatch()
        except Exception:
            pass

    def _on_sound_emitters_status(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(
                getattr(event, "payload", None) or {}
            )
            emitters = payload.get("emitters")
            if isinstance(emitters, list):
                self._state["soundEmitters"] = emitters
                self._dispatch()
        except Exception:
            pass

    def _on_navmesh_mode_status(self, event) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(
                getattr(event, "payload", None) or {}
            )
            mode = payload.get("mode")
            status = payload.get("status")
            if mode:
                self._state["navmeshMode"] = str(mode)
            if status == "baking":
                self._state["navmeshBaking"] = True
            elif status in ("ready", "error"):
                self._state["navmeshBaking"] = False
        except Exception:
            pass


# Process singleton so other extensions (e.g. navmesh_route) can publish keys.
_g_world_state_sync: Optional[WorldStateSyncService] = None


def register_world_state_sync_service(svc: Optional[WorldStateSyncService]) -> None:
    global _g_world_state_sync
    _g_world_state_sync = svc


def get_world_state_sync_service() -> Optional[WorldStateSyncService]:
    return _g_world_state_sync
