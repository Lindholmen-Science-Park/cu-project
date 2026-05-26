from __future__ import annotations

import omni.ext
import omni.usd
import carb
import carb.eventdispatcher

from .payload_orchestrator import PayloadOrchestrator


class PayloadOrchestratorExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str) -> None:
        self._ext_id = ext_id
        self._orchestrator = PayloadOrchestrator()
        PayloadOrchestrator._instance = self._orchestrator

        self._orchestrator.start(lambda: omni.usd.get_context().get_stage())

        ed = carb.eventdispatcher.get_eventdispatcher()
        self._stage_event_sub = ed.observe_event(
            observer_name="younite.payload_orchestrator_core_extension/stage_events",
            event_name="omni.usd@stage_event",
            on_event=self._on_stage_event,
            order=0,
        )

        print("[PayloadOrchestrator] scheduler started")

    def on_shutdown(self) -> None:
        self._orchestrator.stop()
        PayloadOrchestrator._instance = None
        self._stage_event_sub = None
        carb.log_info("[PayloadOrchestratorExtension] Shutdown")

    def _on_stage_event(self, event) -> None:
        if event.type == int(omni.usd.StageEventType.OPENED):
            self._orchestrator.start(lambda: omni.usd.get_context().get_stage())
        elif event.type == int(omni.usd.StageEventType.CLOSED):
            self._orchestrator.stop()
