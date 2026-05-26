"""
Bot Waypoint Mover

Moves a USD prim along a polyline of waypoints each frame.
Simplified variant of the NPC controller's NpcMover — no loop support,
tailored for maintenance bot point-to-point travel.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

Vec3 = Tuple[float, float, float]

DEFAULT_SPEED = 200.0
ARRIVE_THRESHOLD = 30.0
TURN_RATE_DEG_S = 360.0
LOOK_AHEAD_DIST = 400.0


class BotMover:
    """Drives a single bot prim along a waypoint polyline."""

    def __init__(self, *, bot_id: str, speed: float = DEFAULT_SPEED):
        self.bot_id = bot_id
        self.speed = float(speed)

        self._waypoints: List[Vec3] = []
        self._wp_idx: int = 0
        self._active: bool = False
        self._height_offset: Optional[float] = None

        self._pos_x: float = 0.0
        self._pos_z: float = 0.0
        self._current_yaw: float = 0.0
        self._initialized: bool = False

    @property
    def is_active(self) -> bool:
        return self._active

    def set_waypoints(self, waypoints: List[Vec3]) -> None:
        if len(waypoints) < 2:
            return
        self._waypoints = list(waypoints)
        self._wp_idx = 0
        self._height_offset = None
        self._initialized = False
        self._active = True

    def stop(self) -> None:
        self._active = False
        self._waypoints = []
        self._wp_idx = 0
        self._height_offset = None
        self._initialized = False

    @staticmethod
    def _dist_xz(a: Vec3, b: Vec3) -> float:
        dx = a[0] - b[0]
        dz = a[2] - b[2]
        return math.sqrt(dx * dx + dz * dz)

    def _look_ahead_dir(self, cur: Vec3, start_idx: int) -> Tuple[float, float]:
        wps = self._waypoints
        budget = LOOK_AHEAD_DIST
        prev: Vec3 = cur
        target: Vec3 = wps[start_idx] if start_idx < len(wps) else wps[-1]

        for i in range(start_idx, len(wps)):
            seg_len = self._dist_xz(prev, wps[i])
            if seg_len <= 1e-6:
                prev = wps[i]
                continue
            if budget <= seg_len:
                t = budget / seg_len
                target = (
                    prev[0] + (wps[i][0] - prev[0]) * t,
                    prev[1] + (wps[i][1] - prev[1]) * t,
                    prev[2] + (wps[i][2] - prev[2]) * t,
                )
                break
            budget -= seg_len
            prev = wps[i]
            target = wps[i]

        dx = target[0] - cur[0]
        dz = target[2] - cur[2]
        mag = math.sqrt(dx * dx + dz * dz)
        if mag < 1e-6:
            return 0.0, -1.0
        return dx / mag, dz / mag

    def update(self, dt: float, current_world_pos: Vec3) -> Optional[Tuple[Vec3, Vec3]]:
        """Advance the bot. Returns (translate, rotateXYZ) or None if inactive."""
        if not self._active or not self._waypoints:
            return None

        if not self._initialized:
            self._pos_x = current_world_pos[0]
            self._pos_z = current_world_pos[2]
            self._height_offset = current_world_pos[1] - self._waypoints[0][1]
            self._initialized = True

        idx = self._wp_idx
        pos_x = self._pos_x
        pos_z = self._pos_z

        if idx < len(self._waypoints) and self._dist_xz(
            (pos_x, 0.0, pos_z), self._waypoints[idx]
        ) <= ARRIVE_THRESHOLD:
            pos_x = self._waypoints[idx][0]
            pos_z = self._waypoints[idx][2]
            idx += 1

        if idx >= len(self._waypoints):
            self._active = False
            last = self._waypoints[-1]
            h = self._height_offset or 0.0
            return (last[0], last[1] + h, last[2]), (0.0, self._current_yaw, 0.0)

        budget = self.speed * dt
        height_offset = self._height_offset or 0.0

        while budget > 1e-6 and idx < len(self._waypoints):
            tgt = self._waypoints[idx]
            seg_dx = tgt[0] - pos_x
            seg_dz = tgt[2] - pos_z
            seg_len = math.sqrt(seg_dx * seg_dx + seg_dz * seg_dz)

            if seg_len < 1e-6:
                idx += 1
                continue

            if budget >= seg_len:
                pos_x = tgt[0]
                pos_z = tgt[2]
                budget -= seg_len
                idx += 1
            else:
                t = budget / seg_len
                pos_x += seg_dx * t
                pos_z += seg_dz * t
                budget = 0.0

        self._wp_idx = idx
        self._pos_x = pos_x
        self._pos_z = pos_z

        h_idx = min(idx, len(self._waypoints) - 1)
        new_y = self._waypoints[h_idx][1] + height_offset

        look_idx = min(idx, len(self._waypoints) - 1)
        la_x, la_z = self._look_ahead_dir((pos_x, new_y, pos_z), look_idx)
        target_yaw = math.degrees(math.atan2(-la_x, -la_z))

        delta = (target_yaw - self._current_yaw + 180.0) % 360.0 - 180.0
        max_step = TURN_RATE_DEG_S * dt
        if abs(delta) > max_step:
            delta = max_step if delta > 0.0 else -max_step
        self._current_yaw += delta

        return (pos_x, new_y, pos_z), (0.0, self._current_yaw, 0.0)
