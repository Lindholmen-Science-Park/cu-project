"""Per-floor landing (outer) doors — one persistent controller per floor."""

from typing import Dict, Optional

from .door_pair_controller import DoorPairController, DoorPairStops

LANDING_DOOR_STOPS = DoorPairStops(
    door1_closed=19.18064,
    door1_middle=19.6866,
    door1_open=20.21453,
    door2_closed=19.6866,
    door2_open=20.21453,
)


class LandingDoorService:
    def __init__(
        self,
        payload_root: str = "/World/elevator_edit",
        door_open_duration_sec: float = 1.8,
        door_close_duration_sec: float = 2.2,
    ):
        self._payload_root = payload_root.rstrip("/")
        self._open_duration = max(0.2, float(door_open_duration_sec))
        self._close_duration = max(0.2, float(door_close_duration_sec))
        self._floor_open: Dict[int, bool] = {0: False, 1: False}
        self._controllers: Dict[int, DoorPairController] = {}
        for f in (0, 1):
            p1, p2 = self._paths_static(self._payload_root, f)
            self._controllers[f] = DoorPairController(
                p1,
                p2,
                LANDING_DOOR_STOPS,
                open_duration_sec=self._open_duration,
                close_duration_sec=self._close_duration,
            )

    @staticmethod
    def _paths_static(payload_root: str, floor: int):
        f = int(floor)
        return (
            f"{payload_root}/floor_{f}_landing_door_1",
            f"{payload_root}/floor_{f}_landing_door_2",
        )

    def _controller(self, floor: int) -> DoorPairController:
        return self._controllers[int(floor)]

    def _prepare_open(self, ctrl: DoorPairController) -> None:
        from .door_pair_controller import is_pair_open

        ctrl.sync_open_state_from_stage()
        if not ctrl.is_open:
            return
        t1, e1 = ctrl._read_translate(ctrl.door1_path)
        t2, e2 = ctrl._read_translate(ctrl.door2_path)
        if e1 or e2:
            return
        if not is_pair_open(float(t1[0]), float(t2[0]), ctrl.stops):
            ctrl._is_open = False

    def _prepare_close(self, ctrl: DoorPairController) -> None:
        from .door_pair_controller import is_pair_closed

        ctrl.sync_open_state_from_stage()
        if ctrl.is_open:
            return
        t1, e1 = ctrl._read_translate(ctrl.door1_path)
        t2, e2 = ctrl._read_translate(ctrl.door2_path)
        if e1 or e2:
            ctrl._is_open = True
            return
        if not is_pair_closed(float(t1[0]), float(t2[0]), ctrl.stops):
            ctrl._is_open = True

    @property
    def is_animating(self) -> bool:
        return any(c.is_animating for c in self._controllers.values())

    def is_floor_open(self, floor: int) -> bool:
        return bool(self._floor_open.get(int(floor), False))

    def request_open(self, floor: int) -> dict:
        f = int(floor)
        if f not in self._controllers:
            return {"error": "floor must be 0 or 1"}
        if self.is_animating:
            return {"error": "landing doors already moving"}
        if self._floor_open.get(f):
            return {"error": f"floor {f} landing doors already open"}

        ctrl = self._controller(f)
        self._prepare_open(ctrl)
        result = ctrl.request_open()
        if "error" in result:
            return result
        return {"ok": True, "floor": f, "action": "open"}

    def request_close(self, floor: int) -> dict:
        f = int(floor)
        if f not in self._controllers:
            return {"error": "floor must be 0 or 1"}
        if self.is_animating:
            return {"error": "landing doors already moving"}
        if not self._floor_open.get(f):
            return {"error": f"floor {f} landing doors already closed"}

        ctrl = self._controller(f)
        self._prepare_close(ctrl)
        result = ctrl.request_close()
        if "error" in result:
            return result
        return {"ok": True, "floor": f, "action": "close"}

    def reset_animation(self) -> None:
        for ctrl in self._controllers.values():
            ctrl.reset_animation()

    def sync_floor_states_from_stage(self) -> None:
        for f in self._controllers:
            ctrl = self._controller(f)
            ctrl.sync_open_state_from_stage()
            self._floor_open[f] = ctrl.is_open

    def update(self, dt: float) -> bool:
        changed = False
        for f, ctrl in self._controllers.items():
            if not ctrl.is_animating:
                continue
            if ctrl.update(dt):
                changed = True
            if not ctrl.is_animating:
                self._floor_open[f] = ctrl.is_open
        return changed

    def get_floor_state(self, floor: int) -> dict:
        f = int(floor)
        ctrl = self._controller(f)
        state = ctrl.get_state()
        state["floor"] = f
        state["open"] = self.is_floor_open(f)
        state["animating"] = ctrl.is_animating
        return state
