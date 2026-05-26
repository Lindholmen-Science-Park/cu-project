from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


BoundsType = Tuple[Tuple[float, float, float], Tuple[float, float, float]]


@dataclass
class SpatialTrigger:
    trigger_id: str
    position: Tuple[float, float, float]
    trigger_type: str = "proximity"       # proximity | volume
    radius: float = 150.0
    xz_only: bool = False
    one_shot: bool = True
    activation: str = "always"            # always | onDemand
    behaviors: List[Dict[str, Any]] = field(default_factory=list)
    bounds: Optional[BoundsType] = None   # AABB for volume triggers
    triggered: bool = False
    active: bool = True


class SpatialTriggerService:
    """
    Manages spatial triggers: proximity spheres / XZ circles and AABB volumes.

    Every frame the extension calls ``update()``; the service checks each
    active trigger against the current player position and fires callbacks
    when conditions are met.
    """

    def __init__(
        self,
        *,
        get_player_position: Callable[[], Optional[Tuple[float, float, float]]],
        meters_per_unit: float = 0.01,
    ):
        self._get_player_position = get_player_position
        self._meters_per_unit = meters_per_unit
        self._triggers: Dict[str, SpatialTrigger] = {}
        self._on_enter_callbacks: List[Callable[[SpatialTrigger], None]] = []

    @property
    def meters_per_unit(self) -> float:
        return self._meters_per_unit

    @meters_per_unit.setter
    def meters_per_unit(self, value: float) -> None:
        self._meters_per_unit = value if value > 0 else 0.01

    def add_trigger(
        self,
        trigger_id: str,
        position: Tuple[float, float, float],
        *,
        trigger_type: str = "proximity",
        radius: float = 150.0,
        radius_meters: Optional[float] = None,
        xz_only: bool = False,
        one_shot: bool = True,
        activation: str = "always",
        behaviors: Optional[List[Dict[str, Any]]] = None,
        bounds: Optional[BoundsType] = None,
        active: bool = True,
    ) -> None:
        if radius_meters is not None and radius_meters > 0:
            mpu = self._meters_per_unit if self._meters_per_unit > 0 else 0.01
            radius = radius_meters / mpu

        self._triggers[trigger_id] = SpatialTrigger(
            trigger_id=trigger_id,
            position=position,
            trigger_type=trigger_type,
            radius=radius,
            xz_only=xz_only,
            one_shot=one_shot,
            activation=activation,
            behaviors=behaviors or [],
            bounds=bounds,
            active=active,
        )

    def remove_trigger(self, trigger_id: str) -> bool:
        return self._triggers.pop(trigger_id, None) is not None

    def clear_all(self) -> None:
        self._triggers.clear()

    def activate(self, trigger_id: str) -> bool:
        t = self._triggers.get(trigger_id)
        if t:
            t.active = True
            t.triggered = False
            return True
        return False

    def deactivate(self, trigger_id: str) -> bool:
        t = self._triggers.get(trigger_id)
        if t:
            t.active = False
            return True
        return False

    def update_position(self, trigger_id: str, position: Tuple[float, float, float]) -> bool:
        """Move an existing (untriggered) trigger to a new position."""
        t = self._triggers.get(trigger_id)
        if t and not t.triggered:
            t.position = position
            return True
        return False

    def on_enter(self, callback: Callable[[SpatialTrigger], None]) -> None:
        self._on_enter_callbacks.append(callback)

    # ------------------------------------------------------------------

    def update(self, _dt: float = 0.0) -> None:
        if not self._triggers:
            return

        pos = self._get_player_position()
        if pos is None:
            return

        px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])

        for t in list(self._triggers.values()):
            if not t.active or t.triggered:
                continue

            hit = False
            if t.trigger_type == "volume":
                hit = self._check_volume(t, px, py, pz)
            else:
                hit = self._check_proximity(t, px, py, pz)

            if hit:
                t.triggered = True
                for cb in self._on_enter_callbacks:
                    try:
                        cb(t)
                    except Exception:
                        pass
                if t.one_shot:
                    t.active = False

    @staticmethod
    def _check_proximity(t: SpatialTrigger, px: float, py: float, pz: float) -> bool:
        dx = px - float(t.position[0])
        dz = pz - float(t.position[2])
        if t.xz_only:
            dist = (dx * dx + dz * dz) ** 0.5
        else:
            dy = py - float(t.position[1])
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
        return dist <= t.radius

    @staticmethod
    def _check_volume(t: SpatialTrigger, px: float, py: float, pz: float) -> bool:
        if t.bounds is None:
            return False
        min_pt, max_pt = t.bounds
        return (
            min_pt[0] <= px <= max_pt[0]
            and min_pt[1] <= py <= max_pt[1]
            and min_pt[2] <= pz <= max_pt[2]
        )
