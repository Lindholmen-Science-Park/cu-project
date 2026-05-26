from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import uuid


class OpType(Enum):
    LOAD = "load"
    UNLOAD = "unload"
    SHOW = "show"
    HIDE = "hide"


class Priority(Enum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class PayloadOperation:
    prim_path: str
    op_type: OpType
    priority: Priority = Priority.MEDIUM
    source: str = ""
    callback: Optional[Callable] = None
    group: Optional[str] = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __lt__(self, other: "PayloadOperation") -> bool:
        return self.priority.value < other.priority.value
