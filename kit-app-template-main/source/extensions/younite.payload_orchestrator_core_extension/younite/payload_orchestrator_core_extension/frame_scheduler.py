from __future__ import annotations

import heapq
import carb
import carb.eventdispatcher
from pxr import UsdGeom

from .operation import PayloadOperation, OpType, Priority
from .performance_monitor import PerformanceMonitor


class FrameScheduler:
    """Drains a priority queue of PayloadOperations each frame within a time budget."""

    def __init__(self, perf_monitor: PerformanceMonitor) -> None:
        self._perf = perf_monitor
        self._queue: list[tuple[int, int, PayloadOperation]] = []
        self._seq = 0
        self._sub = None
        self._stage_fn = None

    def start(self, get_stage_fn) -> None:
        self._stage_fn = get_stage_fn
        import omni.kit.app
        ed = carb.eventdispatcher.get_eventdispatcher()
        self._sub = ed.observe_event(
            observer_name="younite.payload_orchestrator_core_extension/frame_scheduler/update",
            event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
            on_event=self._on_update,
            order=0,
        )

    def stop(self) -> None:
        self._sub = None
        self._stage_fn = None

    def enqueue(self, op: PayloadOperation) -> None:
        self._seq += 1
        heapq.heappush(self._queue, (op.priority.value, self._seq, op))

    def cancel(self, request_id: str) -> bool:
        for i, (_, _, op) in enumerate(self._queue):
            if op.request_id == request_id:
                self._queue[i] = self._queue[-1]
                self._queue.pop()
                heapq.heapify(self._queue)
                return True
        return False

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    def _on_update(self, _event) -> None:
        if not self._queue:
            return

        stage = self._stage_fn() if self._stage_fn else None
        if stage is None:
            return

        self._perf.begin_tick()
        executed = 0

        while self._queue:
            _, _, op = self._queue[0]
            is_critical = op.priority == Priority.CRITICAL
            if not is_critical and executed > 0 and self._perf.elapsed_ms() >= self._perf.frame_budget_ms:
                break

            heapq.heappop(self._queue)
            self._execute(stage, op)
            executed += 1

        self._perf.end_tick(executed)

    def _execute(self, stage, op: PayloadOperation) -> None:
        prim = stage.GetPrimAtPath(op.prim_path)
        if not prim.IsValid():
            carb.log_warn(f"[PayloadOrchestrator] Prim not found: {op.prim_path} (source={op.source})")
            self._fire_callback(op, success=False)
            return

        try:
            if op.op_type == OpType.SHOW:
                UsdGeom.Imageable(prim).MakeVisible()
            elif op.op_type == OpType.HIDE:
                UsdGeom.Imageable(prim).MakeInvisible()
            elif op.op_type == OpType.LOAD:
                prim.Load()
            elif op.op_type == OpType.UNLOAD:
                prim.Unload()
            self._fire_callback(op, success=True)
        except Exception as exc:
            carb.log_error(f"[PayloadOrchestrator] Failed {op.op_type.value} on {op.prim_path}: {exc}")
            self._fire_callback(op, success=False)

    @staticmethod
    def _fire_callback(op: PayloadOperation, *, success: bool) -> None:
        if op.callback is not None:
            try:
                op.callback(op.request_id, success)
            except Exception as exc:
                carb.log_error(f"[PayloadOrchestrator] Callback error for {op.request_id}: {exc}")
