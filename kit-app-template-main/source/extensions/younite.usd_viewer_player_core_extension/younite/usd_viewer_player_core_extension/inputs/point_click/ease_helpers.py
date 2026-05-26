from __future__ import annotations

import math


def smoothstep01(t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return t * t * (3.0 - 2.0 * t)


def smootherstep01(t: float) -> float:
    """Ken Perlin smootherstep — gentler accel/decel than smoothstep (zero 1st/2nd deriv at ends)."""
    t = max(0.0, min(1.0, float(t)))
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def ease_scale_traveled(
    traveled: float,
    total: float,
    *,
    zone_in: float,
    zone_out: float,
    min_scale: float,
    cap_in_frac: float = 0.15,
    cap_out_frac: float = 0.25,
) -> float:
    """Smoothstep ease-in/out from distance along a path (0..1 scale)."""
    total = float(total)
    if total <= 1e-6:
        return 1.0
    floor = float(min_scale)
    zone_in = min(float(zone_in), total * float(cap_in_frac))
    zone_out = min(float(zone_out), total * float(cap_out_frac))
    traveled = max(0.0, float(traveled))
    remaining = max(0.0, total - traveled)
    if zone_in <= 1e-6:
        ease_in = 1.0
    else:
        ease_in = floor + (1.0 - floor) * smoothstep01(traveled / zone_in)
    if zone_out <= 1e-6:
        ease_out = 1.0
    else:
        ease_out = floor + (1.0 - floor) * smoothstep01(remaining / zone_out)
    return max(floor, min(1.0, ease_in * ease_out))


def ease_scale_remaining(
    remaining: float,
    initial: float,
    *,
    zone: float,
    min_scale: float,
    zone_cap_fraction: float = 0.5,
) -> float:
    """Smoothstep ease-in/out from angular (or scalar) remaining vs initial span."""
    initial = abs(float(initial))
    if initial <= 1e-6:
        return 1.0
    floor = float(min_scale)
    cap = max(0.05, min(1.0, float(zone_cap_fraction)))
    zone = min(float(zone), initial * cap)
    if zone <= 1e-6:
        return 1.0
    remaining = abs(float(remaining))
    traveled = max(0.0, initial - remaining)
    ease_in = floor + (1.0 - floor) * smoothstep01(traveled / zone)
    ease_out = floor + (1.0 - floor) * smoothstep01(remaining / zone)
    return max(floor, min(1.0, ease_in * ease_out))


def apply_exponential_coast(
    velocity: float,
    dt: float,
    *,
    decay_per_sec: float,
    stop_vel: float,
) -> tuple[float, float, float]:
    """
    Integrate one frame of velocity coast. Returns (delta, new_velocity, still_active).
    """
    dt = max(float(dt or 0.0), 1.0 / 240.0)
    vel = float(velocity)
    if abs(vel) <= float(stop_vel):
        return 0.0, 0.0, False
    delta = vel * dt
    vel *= math.exp(-float(decay_per_sec) * dt)
    if abs(vel) < float(stop_vel):
        vel = 0.0
    return delta, vel, abs(vel) > float(stop_vel)
