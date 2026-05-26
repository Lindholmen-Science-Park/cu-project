"""Precomputed cab trip from exact start/end and Aalto / KDL16 motion parameters."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .motion_profile import MotionProfileParams, advance_motion

# Fine step for planning only (runtime samples this curve; does not re-integrate).
_PLAN_DT = 1.0 / 240.0
_MAX_PLAN_SEC = 120.0


@dataclass(frozen=True)
class TripPlan:
    """Time-parameterized move: positions are exact at t=0 and t=duration."""

    start: float
    end: float
    duration: float
    peak_speed: float
    decel_start_pos: float
    times: Tuple[float, ...]
    positions: Tuple[float, ...]
    velocities: Tuple[float, ...]


def _find_decel_start_pos(
    start: float,
    end: float,
    positions: List[float],
    velocities: List[float],
) -> float:
    going_up = end > start
    peak_v = 0.0
    peak_i = 0
    for i, v in enumerate(velocities):
        av = abs(v)
        if av > peak_v + 1e-9:
            peak_v = av
            peak_i = i
    for i in range(peak_i + 1, len(velocities)):
        if going_up and velocities[i] < velocities[i - 1] - 1e-6:
            return positions[i]
        if not going_up and velocities[i] > velocities[i - 1] + 1e-6:
            return positions[i]
    return positions[peak_i] if positions else start


def build_trip_plan(
    start: float,
    end: float,
    params: MotionProfileParams,
    *,
    v_cap_override: Optional[float] = None,
) -> TripPlan:
    """
    Plan a full move using the same jerk-limited integrator as the KONE reference
    (v_nom or ``v_cap_override``, accel/decel, jerk, reduced-speed approach zone).
    The curve ends exactly
    at ``end`` with zero velocity — deceleration begins where braking distance
    requires it, not via a runtime snap.
    """
    start = float(start)
    end = float(end)
    pos, vel, acc = start, 0.0, 0.0
    times: List[float] = [0.0]
    positions: List[float] = [start]
    velocities: List[float] = [0.0]
    t = 0.0

    while t < _MAX_PLAN_SEC:
        pos, vel, acc, arrived = advance_motion(
            pos, vel, acc, end, _PLAN_DT, params, v_cap_override=v_cap_override
        )
        t += _PLAN_DT
        times.append(t)
        positions.append(pos)
        velocities.append(vel)
        if arrived:
            break

    if not (
        abs(positions[-1] - end) <= params.stop_eps + 1e-9
        and abs(velocities[-1]) < 1e-6
    ):
        positions[-1] = end
        velocities[-1] = 0.0

    peak_speed = max(abs(v) for v in velocities)
    decel_start = _find_decel_start_pos(start, end, positions, velocities)

    return TripPlan(
        start=start,
        end=end,
        duration=times[-1],
        peak_speed=peak_speed,
        decel_start_pos=decel_start,
        times=tuple(times),
        positions=tuple(positions),
        velocities=tuple(velocities),
    )


def sample_trip_plan(
    plan: TripPlan,
    elapsed: float,
) -> Tuple[float, float, bool]:
    """
    Sample planned position and velocity at ``elapsed`` seconds into the move.

    Returns (position, velocity, finished).
    """
    elapsed = max(0.0, float(elapsed))
    if elapsed >= plan.duration:
        return plan.end, 0.0, True

    times = plan.times
    if elapsed <= times[0]:
        return plan.positions[0], plan.velocities[0], False

    lo, hi = 0, len(times) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if times[mid] <= elapsed:
            lo = mid
        else:
            hi = mid

    t0, t1 = times[lo], times[hi]
    if t1 <= t0 + 1e-12:
        return plan.positions[hi], plan.velocities[hi], False

    u = (elapsed - t0) / (t1 - t0)
    p0, p1 = plan.positions[lo], plan.positions[hi]
    v0, v1 = plan.velocities[lo], plan.velocities[hi]
    pos = p0 + (p1 - p0) * u
    vel = v0 + (v1 - v0) * u
    if plan.end > plan.start:
        pos = min(pos, plan.end)
    elif plan.end < plan.start:
        pos = max(pos, plan.end)
    return pos, vel, False


def theoretical_braking_distance(velocity: float, decel: float) -> float:
    """Distance needed to stop from ``velocity`` at constant decel (v² / 2a)."""
    v = abs(float(velocity))
    a = max(1e-9, float(decel))
    return (v * v) / (2.0 * a)
