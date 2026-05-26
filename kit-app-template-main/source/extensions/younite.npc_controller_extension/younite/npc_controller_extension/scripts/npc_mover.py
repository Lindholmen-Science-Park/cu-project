"""
NPC Waypoint Mover

Moves a USD prim along a polyline of waypoints each frame.
Handles XZ interpolation, height from the path, and smooth yaw rotation
so the character faces the direction of travel.

Designed to mirror the player PointClickAutoMover pattern but stripped of
camera/input concerns — this is purely about driving a prim's transform.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

Vec3 = Tuple[float, float, float]

# Stage units are centimeters (metersPerUnit = 0.01)
DEFAULT_SPEED = 150.0        # cm/s — comfortable walking pace
ARRIVE_THRESHOLD = 30.0      # cm — snap to waypoint when this close
TURN_RATE_DEG_S = 360.0      # max degrees/s yaw change (instant for NPCs)
LOOK_AHEAD_DIST = 400.0      # cm — smooth rotation by aiming further ahead


class NpcMover:
    """Drives a single NPC prim along a waypoint polyline."""

    def __init__(
        self,
        *,
        npc_id: str,
        prim_path: str,
        speed: float = DEFAULT_SPEED,
        arrive_threshold: float = ARRIVE_THRESHOLD,
        loop: bool = False,
    ):
        self.npc_id = npc_id
        self.prim_path = prim_path
        self.speed = float(speed)
        self.arrive_threshold = float(arrive_threshold)
        self.loop = bool(loop)

        self._waypoints: List[Vec3] = []
        self._wp_idx: int = 0
        self._active: bool = False
        self._height_offset: Optional[float] = None

        # Current interpolated position (set on first update from prim)
        self._pos_x: float = 0.0
        self._pos_z: float = 0.0
        self._current_yaw: float = 0.0
        self._initialized: bool = False

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def waypoint_count(self) -> int:
        return len(self._waypoints)

    def set_waypoints(self, waypoints: List[Vec3]) -> None:
        if len(waypoints) < 2:
            return
        self._waypoints = list(waypoints)
        self._wp_idx = 0
        self._height_offset = None
        self._initialized = False
        self._active = True

    def stop(self) -> str:
        was_active = self._active
        self._active = False
        self._waypoints = []
        self._wp_idx = 0
        self._height_offset = None
        self._initialized = False
        return "stopped" if was_active else "idle"

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dist_xz(a: Vec3, b: Vec3) -> float:
        dx = a[0] - b[0]
        dz = a[2] - b[2]
        return math.sqrt(dx * dx + dz * dz)

    def _look_ahead_direction(self, cur: Vec3, start_idx: int) -> Tuple[float, float]:
        """Walk LOOK_AHEAD_DIST along remaining path to get a smooth aim direction."""
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

    # ------------------------------------------------------------------
    # Per-frame update — returns (new_translate, new_rotateXYZ) or None
    # ------------------------------------------------------------------

    def update(self, dt: float, current_world_pos: Vec3) -> Optional[Tuple[Vec3, Vec3]]:
        """
        Advance the NPC along its waypoints by *dt* seconds.

        Args:
            dt: Frame delta time in seconds.
            current_world_pos: The prim's current world-space translation.

        Returns:
            ``(translate, rotateXYZ)`` to apply to the prim, or ``None`` if
            the mover is inactive / already arrived.
        """
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

        # Snap to current target if close enough
        if idx < len(self._waypoints) and self._dist_xz(
            (pos_x, 0.0, pos_z), self._waypoints[idx]
        ) <= self.arrive_threshold:
            pos_x = self._waypoints[idx][0]
            pos_z = self._waypoints[idx][2]
            idx += 1

        if idx >= len(self._waypoints):
            if self.loop and len(self._waypoints) >= 2:
                self._waypoints.reverse()
                idx = 1  # skip index 0 — NPC is already there (was the last waypoint)
            else:
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

        # Handle loop wrap (ping-pong: reverse waypoints)
        if idx >= len(self._waypoints) and self.loop and len(self._waypoints) >= 2:
            self._waypoints.reverse()
            self._wp_idx = 1

        # Height from the nearest target waypoint
        h_idx = min(idx, len(self._waypoints) - 1)
        new_y = self._waypoints[h_idx][1] + height_offset

        # Yaw: face the look-ahead direction (rate-limited)
        look_idx = min(idx, len(self._waypoints) - 1)
        la_x, la_z = self._look_ahead_direction((pos_x, new_y, pos_z), look_idx)
        target_yaw = math.degrees(math.atan2(-la_x, -la_z))

        delta = (target_yaw - self._current_yaw + 180.0) % 360.0 - 180.0
        max_step = TURN_RATE_DEG_S * dt
        if abs(delta) > max_step:
            delta = max_step if delta > 0.0 else -max_step
        self._current_yaw += delta

        return (pos_x, new_y, pos_z), (0.0, self._current_yaw, 0.0)
