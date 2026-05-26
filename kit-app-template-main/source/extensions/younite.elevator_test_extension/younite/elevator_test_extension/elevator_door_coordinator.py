"""Landing + car doors, and automated floor trips (close → move → level → open → dwell → close)."""

from typing import Any, Dict, Optional

from .elevator_call_queue import ElevatorCallQueue
from .elevator_car_door_service import ElevatorCarDoorService
from .elevator_service import ElevatorService
from .landing_door_service import LandingDoorService


class ElevatorDoorCoordinator:
    def __init__(
        self,
        elevator: ElevatorService,
        landing: LandingDoorService,
        car: ElevatorCarDoorService,
        door_dwell_sec: float = 3.0,
    ):
        self._elevator = elevator
        self._landing = landing
        self._car = car
        self._door_dwell_sec = max(0.0, float(door_dwell_sec))
        self._calls = ElevatorCallQueue()
        self._trip: Optional[Dict[str, Any]] = None

    def get_elevator_floor(self) -> Optional[int]:
        return self._elevator.get_current_floor()

    def is_animating(self) -> bool:
        return self._landing.is_animating or self._car.is_animating

    def is_trip_active(self) -> bool:
        return self._trip is not None

    def get_trip_phase(self) -> Optional[str]:
        if not self._trip:
            return None
        return str(self._trip.get("phase"))

    def get_call_state(self) -> dict:
        return self._calls.get_state()

    def is_busy(self) -> bool:
        return (
            self.is_trip_active()
            or self._elevator.is_moving
            or self.is_animating()
        )

    def request_open_floor(self, floor: int) -> dict:
        f = int(floor)
        cab_floor = self.get_elevator_floor()
        sync_car = cab_floor is not None and cab_floor == f

        if self._landing.is_floor_open(f):
            result = {"ok": True, "floor": f, "action": "open", "alreadyOpen": True}
        else:
            result = self._landing.request_open(f)
            if "error" in result:
                return result

        result["elevatorFloor"] = cab_floor
        result["syncedCarDoors"] = False

        if sync_car and not self._car.is_open:
            car_result = self._car.request_open()
            if "error" in car_result:
                result["carDoorError"] = car_result["error"]
            else:
                result["syncedCarDoors"] = True
        elif sync_car and self._car.is_open:
            result["syncedCarDoors"] = True

        return result

    def request_close_floor(self, floor: int) -> dict:
        f = int(floor)
        cab_floor = self.get_elevator_floor()
        sync_car = cab_floor is not None and cab_floor == f

        synced_car = False
        if sync_car and self._car.is_open:
            car_result = self._car.request_close()
            if "error" in car_result:
                return car_result
            synced_car = True

        if self._landing.is_floor_open(f):
            result = self._landing.request_close(f)
            if "error" in result:
                return result
        else:
            result = {"ok": True, "floor": f, "action": "close", "alreadyClosed": True}

        result["elevatorFloor"] = cab_floor
        result["syncedCarDoors"] = synced_car
        return result

    def reset_animation(self) -> None:
        self._trip = None
        self._calls.reset()
        self._landing.reset_animation()
        self._car.reset_animation()

    def sync_states_from_stage(self) -> None:
        self._landing.sync_floor_states_from_stage()
        self._car.sync_open_state_from_stage()

    def update(self, dt: float) -> bool:
        changed = False
        if self._elevator.is_moving:
            changed = self._elevator.update(dt) or changed
        if self._landing.is_animating:
            changed = self._landing.update(dt) or changed
        if self._car.is_animating:
            changed = self._car.update(dt) or changed
        if self._trip:
            changed = self._advance_trip(dt) or changed
        if not self.is_busy() and self._calls.has_pending():
            self._try_dispatch()
        return changed

    def request_hall_call(self, floor: int) -> dict:
        """Landing call at ``floor`` (summon cab there). Lit until cab opens at that floor."""
        try:
            dest = self._calls.register_hall(floor)
        except ValueError as exc:
            return {"error": str(exc)}
        return self._register_and_dispatch(dest, action="hall_call", hallFloor=floor)

    def request_car_call(self, floor: int) -> dict:
        """
        Car panel button — registers destination (stays lit until served).

        During ``dwelling``, cancels open wait and closes; queue continues after.
        """
        f = int(floor)
        if f not in (0, 1):
            return {"error": "floor must be 0 or 1"}

        self._calls.register_car(f)

        if self._trip and self._trip.get("phase") == "dwelling":
            trip_target = int(self._trip["target"])
            self._trip_cancel_dwell()
            return {
                "ok": True,
                "action": "car_call",
                "floor": f,
                "cancelledDwell": True,
                "sameFloorCloseOnly": f == trip_target,
                **self._calls.get_state(),
            }

        if self.is_busy():
            return {
                "ok": True,
                "action": "car_call",
                "floor": f,
                "registered": True,
                **self._calls.get_state(),
            }
        return self._try_dispatch()

    def request_trip_to_floor(self, target_floor: int) -> dict:
        """Register a car destination and dispatch (FIFO) when idle."""
        target = int(target_floor)
        if target not in (0, 1):
            return {"error": "floor must be 0 or 1"}
        if self._trip and self._trip.get("phase") == "dwelling":
            return self.request_car_call(target)
        self._calls.register_car(target)
        if self.is_busy():
            return {
                "ok": True,
                "registered": True,
                "targetFloor": target,
                **self._calls.get_state(),
            }
        return self._try_dispatch()

    def _register_and_dispatch(
        self,
        target: int,
        *,
        action: str = "call",
        **extra: Any,
    ) -> dict:
        if self._trip and self._trip.get("phase") == "dwelling":
            self._calls.register_car(target)
            return self.request_car_call(target)
        if self.is_busy():
            return {
                "ok": True,
                "registered": True,
                "action": action,
                "targetFloor": target,
                **extra,
                **self._calls.get_state(),
            }
        result = self._try_dispatch()
        result["action"] = action
        result.update(extra)
        return result

    def _try_dispatch(self) -> dict:
        """Start the next queued trip when idle, or no-op if queue empty."""
        if self.is_busy():
            return {"ok": True, "busy": True, **self._calls.get_state()}
        current = self.get_elevator_floor()
        if current is None:
            return {"error": "cannot read cab floor"}
        target = self._calls.peek_dispatch_target()
        if target is None:
            return {"ok": True, "idle": True, **self._calls.get_state()}
        return self._begin_trip_to(target)

    def _begin_trip_to(self, target: int) -> dict:
        """Close → move → level → open → dwell → close (or open in place if already there)."""
        target = int(target)
        current = self.get_elevator_floor()
        if current is None:
            return {"error": "cannot read cab floor"}

        if int(current) == target:
            self._trip = {
                "target": target,
                "from_floor": current,
                "phase": "opening",
            }
            result = self.request_open_floor(target)
            if "error" in result:
                self._trip = None
                return {"error": result["error"]}
            return {
                "ok": True,
                "fromFloor": current,
                "targetFloor": target,
                "phase": self._trip["phase"],
                "serveInPlace": True,
                **self._calls.get_state(),
            }

        self._trip = {
            "target": target,
            "from_floor": current,
            "phase": "closing",
        }
        err = self._trip_begin_close(int(current))
        if err:
            self._trip = None
            return {"error": err}
        return {
            "ok": True,
            "fromFloor": current,
            "targetFloor": target,
            "phase": self._trip["phase"],
            **self._calls.get_state(),
        }

    def _trip_begin_close(self, from_floor: int) -> Optional[str]:
        started = False
        if self._landing.is_floor_open(from_floor):
            result = self._landing.request_close(from_floor)
            if "error" in result:
                return result["error"]
            started = True
        if self._car.is_open:
            result = self._car.request_close()
            if "error" in result:
                return result["error"]
            started = True
        if not started and not self.is_animating():
            self._trip["phase"] = "moving"
            self._trip_start_move()
        return None

    def _trip_start_move(self) -> None:
        if not self._trip:
            return
        target = int(self._trip["target"])
        from_floor = int(self._trip["from_floor"])
        direction = 1 if target > from_floor else -1
        result = self._elevator.request_move(direction)
        if "error" in result:
            self._trip["phase"] = "failed"
            self._trip["error"] = result["error"]
        else:
            self._trip["phase"] = "moving"

    def _trip_start_close_destination(self) -> Optional[str]:
        """Close landing + car doors at the trip target (after dwell)."""
        if not self._trip:
            return None
        target = int(self._trip["target"])
        started = False
        if self._landing.is_floor_open(target):
            result = self._landing.request_close(target)
            if "error" in result:
                return result["error"]
            started = True
        cab_floor = self.get_elevator_floor()
        if cab_floor == target and self._car.is_open:
            result = self._car.request_close()
            if "error" in result:
                return result["error"]
            started = True
        if not started and not self.is_animating():
            return None
        return None

    def _trip_enter_close_destination(self) -> None:
        err = self._trip_start_close_destination()
        if err:
            self._trip["phase"] = "failed"
            self._trip["error"] = err
            return
        self._trip["phase"] = "closing_dest"
        if not self.is_animating():
            self._trip_finish_closing_dest()

    def _trip_cancel_dwell(self) -> None:
        if not self._trip or self._trip.get("phase") != "dwelling":
            return
        self._trip["dwell_remaining"] = 0.0
        self._trip_enter_close_destination()

    def _trip_finish_closing_dest(self) -> None:
        self._trip = None

    def _advance_trip(self, dt: float) -> bool:
        if not self._trip:
            return False

        phase = self._trip.get("phase")
        if phase == "failed":
            self._trip = None
            return True

        if phase == "closing":
            if self.is_animating():
                return True
            self._trip["phase"] = "moving"
            self._trip_start_move()
            return True

        if phase == "moving":
            if self._elevator.is_moving:
                if self._elevator.get_motion_phase() == "leveling":
                    self._trip["phase"] = "leveling"
                return True
            self._trip["phase"] = "opening"
            target = int(self._trip["target"])
            result = self.request_open_floor(target)
            if "error" in result:
                self._trip["phase"] = "failed"
                self._trip["error"] = result["error"]
            return True

        if phase == "leveling":
            if self._elevator.is_moving:
                return True
            self._trip["phase"] = "opening"
            target = int(self._trip["target"])
            result = self.request_open_floor(target)
            if "error" in result:
                self._trip["phase"] = "failed"
                self._trip["error"] = result["error"]
            return True

        if phase == "opening":
            if self.is_animating():
                return True
            self._calls.mark_served(int(self._trip["target"]))
            if self._door_dwell_sec > 0.0:
                self._trip["phase"] = "dwelling"
                self._trip["dwell_remaining"] = self._door_dwell_sec
            else:
                self._trip_enter_close_destination()
            return True

        if phase == "dwelling":
            remaining = float(self._trip.get("dwell_remaining", 0.0)) - max(0.0, float(dt))
            self._trip["dwell_remaining"] = remaining
            if remaining > 0.0:
                return True
            self._trip_enter_close_destination()
            return True

        if phase == "closing_dest":
            if self.is_animating():
                return True
            self._trip_finish_closing_dest()
            return True

        return False

    def get_floor_state(self, floor: int) -> dict:
        return self._landing.get_floor_state(floor)

    def get_car_state(self) -> dict:
        return self._car.get_state()

    def is_floor_open(self, floor: int) -> bool:
        return self._landing.is_floor_open(floor)

    def is_car_open(self) -> bool:
        return self._car.is_open

    def request_open_car(self) -> dict:
        """Open inner car doors only (no landing doors)."""
        if self._car.is_animating:
            return {"error": "inner doors already moving"}
        result = self._car.request_open()
        if "error" not in result:
            result["target"] = "car"
        return result

    def request_close_car(self) -> dict:
        """Close inner car doors only (no landing doors)."""
        if self._car.is_animating:
            return {"error": "inner doors already moving"}
        result = self._car.request_close()
        if "error" not in result:
            result["target"] = "car"
        return result
