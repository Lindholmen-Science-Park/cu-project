# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# Central loading phase state for the stage. Allows the player (web client) to
# show step-by-step progress and helps debug when loading gets stuck.

import carb

# Phase identifiers sent to the client (loading.phase event)
PHASE_IDLE = "idle"
PHASE_OPENING_STAGE = "opening_stage"
PHASE_LOADING_ASSETS = "loading_assets"
PHASE_INITIALIZING = "initializing"
PHASE_READY_FOR_PLAYER = "ready_for_player"
PHASE_PLAYER_INITIALIZING = "player_initializing"
PHASE_PREPARING_LIGHTS = "preparing_lights"
PHASE_PREPARING_NAVMESH = "preparing_navmesh"
PHASE_READY = "ready"


class StageLoadingPhase:
    """
    Tracks the current loading phase and notifies the client via loading.phase events.
    StageCore and services call set_phase() at each step so the frontend can show
    "Opening scene...", "Loading assets...", "Preparing player...", etc.
    """

    def __init__(self) -> None:
        self._phase = PHASE_IDLE
        self._message = ""

    def get_phase(self) -> str:
        return self._phase

    def get_message(self) -> str:
        return self._message

    def set_phase(self, phase: str, message: str = "") -> None:
        self._phase = phase
        self._message = message or phase
        try:
            import omni.kit.app as kit_app
            ed = carb.eventdispatcher.get_eventdispatcher()
            type_id = carb.events.type_from_string("loading.phase")
            kit_app.register_event_alias(type_id, "loading.phase")
            payload = {"phase": self._phase, "message": self._message}
            ed.dispatch_event("loading.phase", payload)
            print(f"[stage_core] loading.phase: {self._phase} — {self._message}")
        except Exception:
            pass

    def is_ready(self) -> bool:
        return self._phase == PHASE_READY


# Singleton used by StageWatcher, InitialStageOpenService, extension
stage_loading_phase = StageLoadingPhase()
