import omni.ext


class ElevatorTestExtension(omni.ext.IExt):
    """Composer-only elevator test cube controls."""

    MENU_NAME = "Tools"

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._menu_items = []
        self._stage_sub = None
        self._update_sub = None
        self._panel = None

        import carb.settings

        settings = carb.settings.get_settings()
        prefix = "/exts/younite.elevator_test_extension/"
        prim_path = (
            settings.get_as_string(prefix + "elevator_prim_path")
            or "/World/elevator_edit/elevator_car"
        )
        travel_axis = settings.get_as_string(prefix + "travel_axis") or "z"
        floor_low = settings.get_as_float(prefix + "floor_low")
        if floor_low == 0.0:
            floor_low = -1.26736
        floor_high = settings.get_as_float(prefix + "floor_high")
        if floor_high == 0.0:
            floor_high = 1.74
        payload_root = (
            settings.get_as_string(prefix + "payload_root") or "/World/elevator_edit"
        )

        from .motion_profile import MotionProfileParams
        from .elevator_service import ElevatorService
        from .landing_door_service import LandingDoorService
        from .elevator_car_door_service import ElevatorCarDoorService
        from .elevator_door_coordinator import ElevatorDoorCoordinator
        from .elevator_panel import ElevatorTestPanel

        def _f(key: str, default: float) -> float:
            value = settings.get_as_float(prefix + key)
            return default if value == 0.0 and default != 0.0 else value

        motion = MotionProfileParams(
            v_nom=_f("rated_speed", 1.0),
            v_inspection=_f("inspection_speed", 0.3),
            accel=_f("accel", 0.5),
            decel=_f("decel", 0.5),
            jerk_max=_f("jerk_max", 1.0),
            v_reduced=_f("reduced_speed", 0.8),
            approach_distance=_f("approach_distance", 0.4),
            use_reduced_near_target=settings.get_as_bool(
                prefix + "use_reduced_speed_near_target"
            ),
            stop_eps=_f("stop_eps", 0.005),
            start_delay_sec=_f("start_delay_sec", 0.4),
            stop_delay_sec=_f("stop_delay_sec", 0.4),
            leveling_speed=_f("leveling_speed", 0.2),
            leveling_distance=_f("leveling_distance", 0.05),
        )
        door_open_sec = _f("door_open_duration_sec", 1.8)
        door_close_sec = _f("door_close_duration_sec", 2.2)
        door_dwell_sec = _f("door_dwell_sec", 3.0)

        self._service = ElevatorService(
            prim_path=prim_path,
            travel_axis=travel_axis,
            floor_low=floor_low,
            floor_high=floor_high,
            motion=motion,
        )
        self._landing_doors = LandingDoorService(
            payload_root=payload_root,
            door_open_duration_sec=door_open_sec,
            door_close_duration_sec=door_close_sec,
        )
        self._car_doors = ElevatorCarDoorService(
            car_root=prim_path,
            door_open_duration_sec=door_open_sec,
            door_close_duration_sec=door_close_sec,
        )
        self._door_coordinator = ElevatorDoorCoordinator(
            self._service,
            self._landing_doors,
            self._car_doors,
            door_dwell_sec=door_dwell_sec,
        )
        self._panel = ElevatorTestPanel(self._service, self._door_coordinator)

        self._register_menu()
        self._register_stage_observer()
        self._register_update_loop()

    def on_shutdown(self):
        self._update_sub = None
        if self._stage_sub is not None:
            self._stage_sub = None
        if self._menu_items:
            try:
                import omni.kit.menu.utils as menu_utils

                menu_utils.remove_menu_items(self._menu_items, self.MENU_NAME)
            except Exception:
                pass
            self._menu_items = []
        if self._panel:
            self._panel.destroy()
            self._panel = None

    def _register_menu(self) -> None:
        try:
            from omni.kit.menu.utils import MenuItemDescription
            import omni.kit.menu.utils as menu_utils

            self._menu_items = [
                MenuItemDescription(
                    name="Elevator Test",
                    onclick_fn=lambda: self._panel.show() if self._panel else None,
                    appear_after=[menu_utils.MenuItemOrder.FIRST],
                )
            ]
            menu_utils.add_menu_items(self._menu_items, self.MENU_NAME)
        except Exception as exc:
            print(f"[elevator_test] menu registration failed: {exc}")

    def _register_stage_observer(self) -> None:
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import omni.usd

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _on_stage_event(evt):
                event_type = evt.payload.get("StageEventType")
                if event_type == int(omni.usd.StageEventType.OPENED):
                    self._service.reset_animation()
                    if getattr(self, "_door_coordinator", None):
                        self._door_coordinator.reset_animation()
                        self._door_coordinator.sync_states_from_stage()
                    if self._panel:
                        self._panel.refresh()

            self._stage_sub = ed.observe_event(
                observer_name="younite.elevator_test_extension/stage",
                event_name="omni.usd@stage_event",
                on_event=_on_stage_event,
                order=0,
            )
            try:
                kit_app.register_event_alias(
                    __import__("carb").events.type_from_string("omni.usd@stage_event"),
                    "omni.usd@stage_event",
                )
            except Exception:
                pass
        except Exception as exc:
            print(f"[elevator_test] stage observer failed: {exc}")

    def _register_update_loop(self) -> None:
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app

            ed = carb.eventdispatcher.get_eventdispatcher()
            self._update_sub = ed.observe_event(
                observer_name="younite.elevator_test_extension/update",
                event_name=kit_app.GLOBAL_EVENT_UPDATE,
                on_event=self._on_update,
                order=0,
            )
        except Exception as exc:
            print(f"[elevator_test] update loop failed: {exc}")
            self._update_sub = None

    def _on_update(self, event) -> None:
        dt = float(getattr(event, "payload", {}).get("dt", 1.0 / 60.0))
        changed = False
        coord = getattr(self, "_door_coordinator", None)
        if coord and coord.is_busy():
            changed = coord.update(dt) or changed
        if changed and self._panel:
            self._panel.refresh()
