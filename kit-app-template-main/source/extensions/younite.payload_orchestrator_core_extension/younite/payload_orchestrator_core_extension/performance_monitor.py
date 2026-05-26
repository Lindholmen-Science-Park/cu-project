from __future__ import annotations

import time
from collections import deque


class PerformanceMonitor:
    """Tracks frame times and provides an adaptive per-frame budget for the scheduler."""

    DEFAULT_BUDGET_MS = 4.0
    MIN_BUDGET_MS = 2.0
    MAX_BUDGET_MS = 6.0
    SLOW_FRAME_THRESHOLD_MS = 20.0
    FAST_FRAME_THRESHOLD_MS = 12.0
    HISTORY_SIZE = 60

    def __init__(self) -> None:
        self._frame_times: deque[float] = deque(maxlen=self.HISTORY_SIZE)
        self._budget_ms: float = self.DEFAULT_BUDGET_MS
        self._ops_executed: int = 0
        self._ops_total: int = 0
        self._tick_start: float = 0.0

    @property
    def frame_budget_ms(self) -> float:
        return self._budget_ms

    def begin_tick(self) -> None:
        self._tick_start = time.perf_counter()

    def end_tick(self, ops_executed: int) -> None:
        elapsed = (time.perf_counter() - self._tick_start) * 1000.0
        self._frame_times.append(elapsed)
        self._ops_executed += ops_executed
        self._adapt_budget()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._tick_start) * 1000.0

    def record_request(self) -> None:
        self._ops_total += 1

    def _adapt_budget(self) -> None:
        if len(self._frame_times) < 5:
            return
        avg = sum(self._frame_times) / len(self._frame_times)
        if avg > self.SLOW_FRAME_THRESHOLD_MS:
            self._budget_ms = max(self.MIN_BUDGET_MS, self._budget_ms - 0.5)
        elif avg < self.FAST_FRAME_THRESHOLD_MS:
            self._budget_ms = min(self.MAX_BUDGET_MS, self._budget_ms + 0.25)

    def get_stats(self) -> dict:
        avg = sum(self._frame_times) / len(self._frame_times) if self._frame_times else 0.0
        return {
            "budget_ms": round(self._budget_ms, 2),
            "avg_tick_ms": round(avg, 2),
            "ops_executed": self._ops_executed,
            "ops_total_requested": self._ops_total,
            "history_size": len(self._frame_times),
        }

    def reset(self) -> None:
        self._frame_times.clear()
        self._budget_ms = self.DEFAULT_BUDGET_MS
        self._ops_executed = 0
        self._ops_total = 0
