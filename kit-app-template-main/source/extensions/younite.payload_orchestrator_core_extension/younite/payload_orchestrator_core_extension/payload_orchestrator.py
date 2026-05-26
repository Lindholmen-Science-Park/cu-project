from __future__ import annotations

import uuid
from typing import Callable, List, Optional

import carb

from .operation import PayloadOperation, OpType, Priority
from .frame_scheduler import FrameScheduler
from .performance_monitor import PerformanceMonitor


class PayloadOrchestrator:
    """Central service for queued, frame-budgeted payload and visibility operations."""

    _instance: Optional["PayloadOrchestrator"] = None

    def __init__(self) -> None:
        self._perf = PerformanceMonitor()
        self._scheduler = FrameScheduler(self._perf)

    @classmethod
    def instance(cls) -> "PayloadOrchestrator":
        if cls._instance is None:
            raise RuntimeError("PayloadOrchestrator has not been initialised yet")
        return cls._instance

    def start(self, get_stage_fn) -> None:
        self._scheduler.start(get_stage_fn)
        carb.log_info("[PayloadOrchestrator] Started")

    def stop(self) -> None:
        self._scheduler.stop()
        self._perf.reset()
        carb.log_info("[PayloadOrchestrator] Stopped")

    def request(self, op: PayloadOperation) -> str:
        self._perf.record_request()
        self._scheduler.enqueue(op)
        return op.request_id

    def cancel(self, request_id: str) -> bool:
        return self._scheduler.cancel(request_id)

    def batch(self, ops: List[PayloadOperation], *, group: Optional[str] = None) -> str:
        batch_id = group or uuid.uuid4().hex[:12]
        for op in ops:
            op.group = batch_id
            self.request(op)
        return batch_id

    def get_stats(self) -> dict:
        stats = self._perf.get_stats()
        stats["pending"] = self._scheduler.pending_count
        return stats
