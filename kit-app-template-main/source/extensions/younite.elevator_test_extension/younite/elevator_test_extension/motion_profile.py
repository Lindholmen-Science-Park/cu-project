"""Jerk-limited cab integrator (Aalto / KDL16) — used to *plan* trips, not per-frame runtime."""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class MotionProfileParams:
    """Stage-axis units per second (1 local Z unit ≈ 1 m on the Aalto test rig)."""

    v_nom: float = 1.0
    v_inspection: float = 0.3
    accel: float = 0.5
    decel: float = 0.5
    jerk_max: float = 1.0
    v_reduced: float = 0.8
    approach_distance: float = 0.4
    use_reduced_near_target: bool = True
    stop_eps: float = 0.005
    start_delay_sec: float = 0.4
    stop_delay_sec: float = 0.4
    leveling_speed: float = 0.2
    leveling_distance: float = 0.05


def advance_motion(
    pos: float,
    vel: float,
    acc: float,
    target: float,
    dt: float,
    params: MotionProfileParams,
    *,
    v_cap_override: Optional[float] = None,
) -> Tuple[float, float, float, bool]:
    """
    Integrate one frame toward ``target``.

    Returns (pos, vel, acc, arrived) where ``arrived`` is True when position
    is within ``stop_eps`` and velocity/acceleration are zeroed at the target.
    """
    dt = max(0.0, float(dt))
    if dt <= 0.0:
        return pos, vel, acc, abs(target - pos) <= params.stop_eps and abs(vel) < 1e-9

    dist = target - pos
    dir_sign = 1.0 if dist >= 0.0 else -1.0
    dist_abs = abs(dist)

    if dist_abs <= params.stop_eps:
        return target, 0.0, 0.0, True

    v_cap = float(params.v_nom if v_cap_override is None else v_cap_override)
    if params.use_reduced_near_target and dist_abs <= params.approach_distance:
        v_cap = min(v_cap, params.v_reduced)

    a_lim = max(params.accel, params.decel)
    braking_dist = (vel * vel) / (2.0 * a_lim + 1e-9)

    if dist_abs <= braking_dist:
        a_des = -params.decel * dir_sign
    elif abs(vel) < v_cap:
        a_des = params.accel * dir_sign
    else:
        a_des = 0.0

    j = max(1e-6, params.jerk_max)
    da = a_des - acc
    da_clamped = max(-j * dt, min(j * dt, da))
    acc = acc + da_clamped
    vel = vel + acc * dt
    vel = max(-v_cap, min(v_cap, vel))

    # Never integrate past the floor stop (large Kit dt spikes caused visible overshoot).
    delta = vel * dt
    if abs(delta) > dist_abs:
        delta = dist_abs * dir_sign

    pos = pos + delta

    if abs(target - pos) <= params.stop_eps or abs(delta) >= dist_abs - 1e-12:
        return target, 0.0, 0.0, True

    return pos, vel, acc, False


# Braking rule (same as KONE reference): begin decel when remaining distance <= v²/(2a).
# ``trip_plan.build_trip_plan`` applies this over the full move; runtime samples the result.
