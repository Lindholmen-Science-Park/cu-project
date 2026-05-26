"""Vertical validity checks for shortcut hop exits (elevators)."""
from __future__ import annotations

from .constants import (
    ELEVATOR_BACKTRACK_DY_CM,
    ELEVATOR_BASEMENT_DIP_BELOW_LOW_CM,
    ELEVATOR_EXIT_TO_DEST_MAX_CM,
    ELEVATOR_GOAL_DY_CM,
    ELEVATOR_SAME_BAND_SPAN_CM,
)
from .types import Vec3


def skip_hop_exit_vertical_backtrack(
    start: Vec3,
    end: Vec3,
    exit_pos: Vec3,
    *,
    prefer_mode: bool = False,
    apply_landing_y_check: bool = True,
) -> bool:
    """True if this hop exit should be discarded (wrong-way vertical).

    See shortcuts topic doc for semantics (basement dip, same-band, prefer
    landing-Y for non-seat routes).
    """
    sy = float(start[1])
    ey = float(end[1])
    xy = float(exit_pos[1])
    goal = ey - sy
    span = abs(goal)

    if goal > ELEVATOR_GOAL_DY_CM:
        if xy < sy - ELEVATOR_BACKTRACK_DY_CM:
            return True
    elif goal < -ELEVATOR_GOAL_DY_CM:
        if xy > sy + ELEVATOR_BACKTRACK_DY_CM:
            return True

    if span < ELEVATOR_SAME_BAND_SPAN_CM:
        low = min(sy, ey)
        high = max(sy, ey)
        if xy < low - ELEVATOR_BASEMENT_DIP_BELOW_LOW_CM:
            return True
        if xy > high + ELEVATOR_BASEMENT_DIP_BELOW_LOW_CM:
            return True

    if prefer_mode and apply_landing_y_check:
        if abs(xy - ey) > ELEVATOR_EXIT_TO_DEST_MAX_CM:
            return True
    return False
