"""Inner elevator car doors (child of elevator_car)."""

from typing import Optional

from .door_pair_controller import DoorPairController, DoorPairStops

CAR_DOOR_STOPS = DoorPairStops(
    door1_closed=0.20815,
    door1_middle=-0.21415,
    door1_open=-0.7779,
    door2_closed=-0.29805,
    door2_open=-0.82825,
)


class ElevatorCarDoorService:
    def __init__(
        self,
        car_root: str = "/World/elevator_edit/elevator_car",
        door_open_duration_sec: float = 1.8,
        door_close_duration_sec: float = 2.2,
    ):
        self._car_root = car_root.rstrip("/")
        self._controller = DoorPairController(
            f"{self._car_root}/elevator_car_door_1",
            f"{self._car_root}/elevator_car_door_2",
            CAR_DOOR_STOPS,
            open_duration_sec=door_open_duration_sec,
            close_duration_sec=door_close_duration_sec,
        )

    @property
    def is_animating(self) -> bool:
        return self._controller.is_animating

    @property
    def is_open(self) -> bool:
        return self._controller.is_open

    def request_open(self) -> dict:
        self._prepare_for_open()
        return self._controller.request_open()

    def request_close(self) -> dict:
        self._prepare_for_close()
        return self._controller.request_close()

    def _prepare_for_open(self) -> None:
        from .door_pair_controller import is_pair_open

        self.sync_open_state_from_stage()
        if not self._controller.is_open:
            return
        t1, e1 = self._controller._read_translate(self._controller.door1_path)
        t2, e2 = self._controller._read_translate(self._controller.door2_path)
        if e1 or e2:
            return
        if not is_pair_open(float(t1[0]), float(t2[0]), self._controller.stops):
            self._controller._is_open = False

    def _prepare_for_close(self) -> None:
        from .door_pair_controller import is_pair_closed

        self.sync_open_state_from_stage()
        if self._controller.is_open:
            return
        t1, e1 = self._controller._read_translate(self._controller.door1_path)
        t2, e2 = self._controller._read_translate(self._controller.door2_path)
        if e1 or e2:
            self._controller._is_open = True
            return
        if not is_pair_closed(float(t1[0]), float(t2[0]), self._controller.stops):
            self._controller._is_open = True

    def reset_animation(self) -> None:
        self._controller.reset_animation()

    def sync_open_state_from_stage(self) -> None:
        self._controller.sync_open_state_from_stage()

    def update(self, dt: float) -> bool:
        return self._controller.update(dt)

    def get_state(self) -> dict:
        state = self._controller.get_state()
        state["label"] = "car"
        return state
