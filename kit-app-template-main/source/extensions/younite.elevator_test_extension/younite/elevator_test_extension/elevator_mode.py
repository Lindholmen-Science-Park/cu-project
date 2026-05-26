"""Operating modes for the Composer elevator test (KDL16 / maintenance)."""

from enum import Enum


class ElevatorMode(Enum):
    NORMAL = "normal"
    INSPECTION = "inspection"
