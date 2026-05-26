import omni.ui as ui

# Lit call-button colors (car + hall), similar to landing call lanterns.
_STYLE_CALL_OFF = {"background_color": 0xFF3D3D3D, "color": 0xFFDDDDDD}
_STYLE_CALL_ON = {"background_color": 0xFFD4A017, "color": 0xFF101010}


class ElevatorTestPanel:
    """Composer UI for elevator travel and landing + car doors."""

    WINDOW_TITLE = "Elevator Test"

    def __init__(self, elevator_service, door_coordinator=None):
        self._service = elevator_service
        self._doors = door_coordinator
        self._window = None
        self._y_label = None
        self._status_label = None
        self._floor_label = None
        self._cab_floor_label = None
        self._trip_label = None
        self._door_status_label = None
        self._btn_floor0 = None
        self._btn_floor1 = None
        self._btn_refresh = None
        self._btn_toggle_floor0 = None
        self._btn_toggle_floor1 = None
        self._btn_toggle_inner = None
        self._mode_label = None
        self._btn_mode_normal = None
        self._btn_mode_inspection = None
        self._queue_label = None
        self._btn_hall_0 = None
        self._btn_hall_1 = None

    @property
    def visible(self) -> bool:
        return bool(self._window and self._window.visible)

    @visible.setter
    def visible(self, value: bool) -> None:
        if self._window:
            self._window.visible = bool(value)

    def show(self) -> None:
        if self._window is None:
            self._build_window()
        self._window.visible = True
        self.refresh()

    def destroy(self) -> None:
        if self._window:
            self._window.visible = False
            self._window.destroy()
        self._window = None
        self._y_label = None
        self._status_label = None
        self._floor_label = None
        self._cab_floor_label = None
        self._trip_label = None
        self._door_status_label = None
        self._btn_floor0 = None
        self._btn_floor1 = None
        self._btn_refresh = None
        self._btn_toggle_floor0 = None
        self._btn_toggle_floor1 = None
        self._btn_toggle_inner = None
        self._mode_label = None
        self._btn_mode_normal = None
        self._btn_mode_inspection = None
        self._queue_label = None
        self._btn_hall_0 = None
        self._btn_hall_1 = None

    @staticmethod
    def _apply_call_style(btn, lit: bool) -> None:
        if btn is None:
            return
        btn.style = _STYLE_CALL_ON if lit else _STYLE_CALL_OFF

    def _floor_in_list(self, values, floor: int) -> bool:
        return int(floor) in [int(v) for v in values]

    def _update_mode_buttons(self) -> None:
        from .elevator_mode import ElevatorMode

        busy = self._service.is_moving
        if self._doors and self._doors.is_busy():
            busy = True
        mode = self._service.mode
        if self._mode_label is not None:
            cap = self._service.get_state().get("travelSpeedCap", 0.0)
            self._mode_label.text = (
                f"Mode: {mode.value}  (cab cap {cap:.2f} m/s)"
            )
        if self._btn_mode_normal is not None:
            self._btn_mode_normal.enabled = not busy and mode != ElevatorMode.NORMAL
        if self._btn_mode_inspection is not None:
            self._btn_mode_inspection.enabled = (
                not busy and mode != ElevatorMode.INSPECTION
            )

    def _update_floor_buttons(self) -> None:
        trip_phase = self._doors.get_trip_phase() if self._doors else None
        dwelling = trip_phase == "dwelling"
        call_state = self._doors.get_call_state() if self._doors else {}
        lit_car = call_state.get("litCar", call_state.get("litFloors", []))
        lit_hall = call_state.get("litHall", [])

        for floor, btn in ((0, self._btn_floor0), (1, self._btn_floor1)):
            if btn is None:
                continue
            btn.enabled = True
            if dwelling:
                btn.text = f"Floor {floor} — close now"
            else:
                btn.text = f"Floor {floor}"
            self._apply_call_style(btn, self._floor_in_list(lit_car, floor))

        for floor, btn in ((0, self._btn_hall_0), (1, self._btn_hall_1)):
            if btn is None:
                continue
            btn.enabled = True
            btn.text = f"Call floor {floor}"
            self._apply_call_style(btn, self._floor_in_list(lit_hall, floor))

        if self._queue_label is not None and self._doors:
            q = call_state.get("queue", [])
            self._queue_label.text = (
                f"Queue: {q}" if q else "Queue: (empty)"
            )

        if self._btn_refresh is not None:
            self._btn_refresh.enabled = True

    def _door_toggle_label(self, name: str, state: dict) -> str:
        if "error" in state:
            return f"{name}: {state['error']}"
        if state.get("animating"):
            action = "opening" if state.get("open") else "closing"
            return f"{name}: {action}…"
        if state.get("open"):
            return f"Close {name}"
        return f"Open {name}"

    def _update_door_toggle_buttons(self) -> None:
        if not self._doors:
            return
        busy = self._doors.is_busy()

        for floor, btn in (
            (0, self._btn_toggle_floor0),
            (1, self._btn_toggle_floor1),
        ):
            if btn is None:
                continue
            state = self._doors.get_floor_state(floor)
            btn.text = self._door_toggle_label(f"floor {floor} outer", state)
            btn.enabled = not busy and "error" not in state and not state.get("animating")

        if self._btn_toggle_inner is not None:
            state = self._doors.get_car_state()
            self._btn_toggle_inner.text = self._door_toggle_label("inner", state)
            self._btn_toggle_inner.enabled = (
                not busy and "error" not in state and not state.get("animating")
            )

    def refresh(self) -> None:
        if not self._window:
            return
        state = self._service.get_state()
        if "error" in state and "primPath" not in state:
            if self._status_label:
                self._status_label.text = state["error"]
            if self._y_label:
                self._y_label.text = "Z: —"
        else:
            axis = state.get("travelAxis", "Z")
            pos = state.get("position", state.get("z", 0.0))
            if state.get("moving") and "targetPosition" in state:
                target = state["targetPosition"]
                if self._y_label:
                    self._y_label.text = f"{axis}: {pos:.3f}  →  {target:.3f}"
                if self._status_label:
                    self._status_label.text = f"{state.get('primPath', '')}  (moving)"
            else:
                if self._y_label:
                    self._y_label.text = f"{axis}: {pos:.3f}"
                if self._status_label:
                    self._status_label.text = state.get("primPath", "")

            if self._floor_label is not None:
                low = state.get("floorLow", self._service._floor_low)
                high = state.get("floorHigh", self._service._floor_high)
                self._floor_label.text = f"Car stops {low:.5f}  …  {high:.5f}"

            if self._cab_floor_label is not None:
                cab = state.get("currentFloor")
                if cab is None and self._doors:
                    cab = self._doors.get_elevator_floor()
                if cab is None:
                    self._cab_floor_label.text = "Cab floor: —"
                else:
                    self._cab_floor_label.text = f"Cab floor: {int(cab)}"

            if self._trip_label is not None and self._doors:
                phase = self._doors.get_trip_phase()
                if phase:
                    self._trip_label.text = f"Trip: {phase}…"
                elif not self._doors.get_call_state().get("queue"):
                    self._trip_label.text = ""

        self._update_mode_buttons()
        self._update_floor_buttons()
        self._update_door_toggle_buttons()

        if self._doors and self._door_status_label is not None:
            parts = []
            for floor in (0, 1):
                ds = self._doors.get_floor_state(floor)
                if "error" in ds:
                    parts.append(f"F{floor} outer: {ds['error']}")
                else:
                    label = "open" if ds.get("open") else "closed"
                    if ds.get("animating"):
                        label += " (moving)"
                    parts.append(f"F{floor} outer: {label}")
            cs = self._doors.get_car_state()
            if "error" in cs:
                parts.append(f"inner: {cs['error']}")
            else:
                label = "open" if cs.get("open") else "closed"
                if cs.get("animating"):
                    label += " (moving)"
                parts.append(f"inner: {label}")
            self._door_status_label.text = "  |  ".join(parts)

    def _build_window(self) -> None:
        self._window = ui.Window(
            self.WINDOW_TITLE,
            width=340,
            height=600,
            visible=True,
            dockPreference=ui.DockPreference.RIGHT_BOTTOM,
        )

        with self._window.frame:
            with ui.VStack(spacing=8, height=0):
                ui.Label("Elevator car", style={"font_size": 14})
                ui.Label(
                    "In-car floor buttons and landing call buttons (per floor). Lit until "
                    "served; FIFO queue. During dwell, in-car buttons close immediately.",
                    word_wrap=True,
                )
                self._status_label = ui.Label(self._service.prim_path)
                self._y_label = ui.Label("Z: —")
                self._cab_floor_label = ui.Label("")
                self._trip_label = ui.Label("")

                ui.Spacer(height=4)
                ui.Label("Operating mode", style={"font_size": 14})
                self._mode_label = ui.Label("Mode: normal")
                with ui.HStack(spacing=6):
                    self._btn_mode_normal = ui.Button(
                        "Normal (1.0 m/s)",
                        clicked_fn=lambda: self._on_set_mode("normal"),
                    )
                    self._btn_mode_inspection = ui.Button(
                        "Inspection (0.3 m/s)",
                        clicked_fn=lambda: self._on_set_mode("inspection"),
                    )

                self._btn_floor0 = ui.Button(
                    "Floor 0",
                    clicked_fn=lambda: self._on_trip(0),
                )
                self._btn_floor1 = ui.Button(
                    "Floor 1",
                    clicked_fn=lambda: self._on_trip(1),
                )
                self._queue_label = ui.Label("Queue: (empty)")

                ui.Spacer(height=4)
                ui.Label("Landing calls", style={"font_size": 14})
                self._btn_hall_0 = ui.Button(
                    "Call floor 0",
                    clicked_fn=lambda: self._on_hall_call(0),
                )
                self._btn_hall_1 = ui.Button(
                    "Call floor 1",
                    clicked_fn=lambda: self._on_hall_call(1),
                )

                self._btn_refresh = ui.Button("Refresh", clicked_fn=self.refresh)

                self._floor_label = ui.Label("")

                if self._doors:
                    ui.Spacer(height=8)
                    ui.Label("Landing doors (outer)", style={"font_size": 14})
                    ui.Label(
                        "Manual override — each button toggles open/close.",
                        word_wrap=True,
                    )
                    self._btn_toggle_floor0 = ui.Button(
                        "Open floor 0 outer",
                        clicked_fn=lambda: self._on_toggle_door(0),
                    )
                    self._btn_toggle_floor1 = ui.Button(
                        "Open floor 1 outer",
                        clicked_fn=lambda: self._on_toggle_door(1),
                    )

                    ui.Spacer(height=8)
                    ui.Label("Car doors (inner)", style={"font_size": 14})
                    self._btn_toggle_inner = ui.Button(
                        "Open inner",
                        clicked_fn=self._on_toggle_car_door,
                    )

                    self._door_status_label = ui.Label("")

        self.refresh()

    def _on_set_mode(self, mode_name: str) -> None:
        from .elevator_mode import ElevatorMode

        if self._service.is_moving:
            if self._trip_label:
                self._trip_label.text = "Cannot change mode while cab is moving"
            return
        if self._doors and self._doors.is_busy():
            if self._trip_label:
                self._trip_label.text = "Cannot change mode during trip or doors"
            return
        try:
            self._service.set_mode(ElevatorMode(mode_name))
        except ValueError:
            if self._trip_label:
                self._trip_label.text = f"Unknown mode: {mode_name}"
            return
        self.refresh()

    def _format_call_result(self, result: dict, prefix: str) -> str:
        if "error" in result:
            return result["error"]
        if result.get("cancelledDwell"):
            return f"{prefix}: closing now"
        if "fromFloor" in result and "targetFloor" in result:
            return (
                f"{prefix}: F{result.get('fromFloor')} → F{result.get('targetFloor')}"
            )
        if result.get("registered"):
            q = result.get("queue", [])
            return f"{prefix}: queued {q}"
        if result.get("idle"):
            return f"{prefix}: registered (idle)"
        q = result.get("queue", [])
        return f"{prefix}: queue {q}" if q else prefix

    def _on_hall_call(self, floor: int) -> None:
        if not self._doors:
            return
        result = self._doors.request_hall_call(floor)
        if self._trip_label:
            self._trip_label.text = self._format_call_result(
                result, f"Call floor {floor}"
            )
        self.refresh()

    def _on_trip(self, floor: int) -> None:
        if not self._doors:
            return
        phase = self._doors.get_trip_phase()
        if phase == "dwelling":
            result = self._doors.request_car_call(floor)
        else:
            result = self._doors.request_trip_to_floor(floor)
        if self._trip_label:
            self._trip_label.text = self._format_call_result(result, f"Car F{floor}")
        self.refresh()

    def _on_toggle_car_door(self) -> None:
        if not self._doors:
            return
        if self._doors.is_busy():
            if self._door_status_label:
                self._door_status_label.text = "Wait for trip or motion to finish"
            return
        open_doors = not self._doors.is_car_open()
        if open_doors:
            result = self._doors.request_open_car()
        else:
            result = self._doors.request_close_car()
        if self._door_status_label:
            if "error" in result:
                self._door_status_label.text = result["error"]
            else:
                action = "opening" if open_doors else "closing"
                self._door_status_label.text = f"Inner doors {action}"
        self.refresh()

    def _on_toggle_door(self, floor: int) -> None:
        if not self._doors:
            return
        if self._doors.is_busy():
            if self._door_status_label:
                self._door_status_label.text = "Wait for trip or motion to finish"
            return
        open_doors = not self._doors.is_floor_open(floor)
        if open_doors:
            result = self._doors.request_open_floor(floor)
        else:
            result = self._doors.request_close_floor(floor)
        if self._door_status_label:
            if "error" in result:
                self._door_status_label.text = result["error"]
            elif result.get("syncedCarDoors"):
                self._door_status_label.text = (
                    f"Floor {floor}: outer + inner doors moving"
                )
            elif result.get("carDoorError"):
                self._door_status_label.text = (
                    f"Outer moving; inner: {result['carDoorError']}"
                )
            elif result.get("elevatorFloor") != floor:
                self._door_status_label.text = (
                    f"Floor {floor} outer only (cab on floor {result.get('elevatorFloor')})"
                )
        self.refresh()
