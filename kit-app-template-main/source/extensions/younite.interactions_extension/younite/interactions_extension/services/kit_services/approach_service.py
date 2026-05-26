"""Approach-then-act service.

Walks the player to a computed position near a target before firing a
callback.  Reusable for any interaction type that requires the player to be
close before an action triggers (NPCs, interactive objects, etc.).

Usage in ``interactions.json``::

    "approach": { "distanceMeters": 3.0 }

The service is interaction-type-agnostic — it only cares about geometry
and delegates post-arrival behaviour to the caller-provided callback.
"""

from __future__ import annotations

import math
import time
from typing import Callable, Optional, Tuple


class ApproachService:
    """Manage walk-to-target-then-act for interaction clicks."""

    ARRIVAL_BUFFER_METERS: float = 1.0
    TIMEOUT_S: float = 30.0

    def __init__(
        self,
        *,
        get_player_pos: Callable[[], Optional[Tuple[float, float, float]]],
        get_meters_per_unit: Callable[[], float],
    ):
        self._get_player_pos = get_player_pos
        self._get_mpu = get_meters_per_unit
        self._pending: Optional[_PendingApproach] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request(
        self,
        *,
        target_pos: Tuple[float, float, float],
        distance_meters: float,
        on_arrival: Callable[[], None],
        timeout_s: float | None = None,
    ) -> bool:
        """Start an approach toward *target_pos*.

        Returns ``True`` if the player needs to walk (approach queued,
        navigation event dispatched).  Returns ``False`` if the player is
        already close enough — the caller should act immediately.
        """
        player_pos = self._get_player_pos()
        if not player_pos:
            return False

        mpu = self._get_mpu()
        threshold_m = distance_meters + self.ARRIVAL_BUFFER_METERS
        dist_m = _dist_xz(player_pos, target_pos) * mpu

        if dist_m <= threshold_m:
            return False

        approach_pos = _compute_approach_pos(
            target_pos=target_pos,
            player_pos=player_pos,
            offset_meters=distance_meters,
            mpu=mpu,
        )

        self._pending = _PendingApproach(
            target_pos=target_pos,
            approach_pos=approach_pos,
            threshold_units=threshold_m / mpu,
            on_arrival=on_arrival,
            start_time=time.time(),
            timeout_s=timeout_s or self.TIMEOUT_S,
        )

        _dispatch_nav(approach_pos)
        return True

    def cancel(self) -> None:
        """Cancel any pending approach (e.g. when the player clicks elsewhere)."""
        self._pending = None

    def has_pending(self) -> bool:
        return self._pending is not None

    def update(self) -> None:
        """Per-frame check: has the player arrived?"""
        if not self._pending:
            return

        p = self._pending

        if time.time() - p.start_time > p.timeout_s:
            self._pending = None
            return

        player_pos = self._get_player_pos()
        if not player_pos:
            return

        if _dist_xz(player_pos, p.target_pos) <= p.threshold_units:
            callback = p.on_arrival
            self._pending = None
            try:
                callback()
            except Exception as exc:
                print(f"[approach] on_arrival error: {exc}")

    def shutdown(self) -> None:
        self._pending = None


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _dist_xz(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dx = a[0] - b[0]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dz * dz)


def _compute_approach_pos(
    *,
    target_pos: Tuple[float, float, float],
    player_pos: Tuple[float, float, float],
    offset_meters: float,
    mpu: float,
) -> Tuple[float, float, float]:
    """Point that is *offset_meters* from *target_pos* toward *player_pos*."""
    dx = player_pos[0] - target_pos[0]
    dz = player_pos[2] - target_pos[2]
    mag = math.sqrt(dx * dx + dz * dz)
    if mag < 1e-6:
        dx, dz, mag = 0.0, 1.0, 1.0

    offset_units = offset_meters / mpu
    scale = offset_units / mag
    return (
        target_pos[0] + dx * scale,
        target_pos[1],
        target_pos[2] + dz * scale,
    )


def _dispatch_nav(pos: Tuple[float, float, float]) -> None:
    """Trigger the existing navigation pipeline via ``younite.navigation.requestPoint``."""
    try:
        import carb.eventdispatcher

        carb.eventdispatcher.get_eventdispatcher().dispatch_event(
            "younite.navigation.requestPoint",
            {"world": {"x": pos[0], "y": pos[1], "z": pos[2]}},
        )
    except Exception:
        pass


class _PendingApproach:
    __slots__ = (
        "target_pos",
        "approach_pos",
        "threshold_units",
        "on_arrival",
        "start_time",
        "timeout_s",
    )

    def __init__(
        self,
        *,
        target_pos: Tuple[float, float, float],
        approach_pos: Tuple[float, float, float],
        threshold_units: float,
        on_arrival: Callable[[], None],
        start_time: float,
        timeout_s: float,
    ):
        self.target_pos = target_pos
        self.approach_pos = approach_pos
        self.threshold_units = threshold_units
        self.on_arrival = on_arrival
        self.start_time = start_time
        self.timeout_s = timeout_s
