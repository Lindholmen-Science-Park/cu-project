"""FIFO destination queue and lit-call state (car + hall) for the 2-floor test rig."""

from collections import deque
from typing import Deque, Optional, Set


class ElevatorCallQueue:
    """Registers calls, keeps buttons lit until served, dispatches in FIFO order."""

    def __init__(self) -> None:
        self._fifo: Deque[int] = deque()
        self._lit_car: Set[int] = set()
        self._lit_hall: Set[int] = set()

    def register_car(self, floor: int) -> None:
        f = int(floor)
        if f not in (0, 1):
            raise ValueError("floor must be 0 or 1")
        self._lit_car.add(f)
        if f not in self._fifo:
            self._fifo.append(f)

    def register_hall(self, floor: int) -> int:
        """Hall landing at ``floor`` — summon cab to that floor."""
        f = int(floor)
        if f not in (0, 1):
            raise ValueError("floor must be 0 or 1")
        self._lit_hall.add(f)
        self.register_car(f)
        return f

    def register_destination(self, floor: int) -> None:
        """Backward-compatible alias for car registration."""
        self.register_car(floor)

    def mark_served(self, floor: int) -> None:
        """Clear lit state when the cab has arrived at ``floor`` (opening phase)."""
        f = int(floor)
        self._lit_car.discard(f)
        self._lit_hall.discard(f)
        while self._fifo and self._fifo[0] == f:
            self._fifo.popleft()

    def peek_dispatch_target(self) -> Optional[int]:
        """Next FIFO destination (including serve-in-place when head equals cab floor)."""
        if not self._fifo:
            return None
        return int(self._fifo[0])

    def has_pending(self) -> bool:
        return len(self._fifo) > 0

    def get_state(self) -> dict:
        return {
            "queue": list(self._fifo),
            "litFloors": sorted(self._lit_car),
            "litCar": sorted(self._lit_car),
            "litHall": sorted(self._lit_hall),
        }

    def reset(self) -> None:
        self._fifo.clear()
        self._lit_car.clear()
        self._lit_hall.clear()
