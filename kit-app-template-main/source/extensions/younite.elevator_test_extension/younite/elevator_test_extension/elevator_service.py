"""Cab travel on a translate axis — planned move + leveling crawl (Aalto / KDL16)."""

from typing import Optional, Tuple

from .elevator_mode import ElevatorMode
from .motion_profile import MotionProfileParams
from .trip_plan import TripPlan, build_trip_plan, sample_trip_plan

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
_POS_EPS = 1e-4


class ElevatorService:
    def __init__(
        self,
        prim_path: str = "/World/elevator_edit/elevator_car",
        travel_axis: str = "z",
        floor_low: float = -1.26736,
        floor_high: float = 1.74,
        motion: Optional[MotionProfileParams] = None,
    ):
        self._prim_path = prim_path
        axis = str(travel_axis or "z").lower()
        if axis not in _AXIS_INDEX:
            axis = "z"
        self._axis = axis
        self._axis_index = _AXIS_INDEX[axis]
        self._floor_low = float(floor_low)
        self._floor_high = float(floor_high)
        if self._floor_high < self._floor_low:
            self._floor_low, self._floor_high = self._floor_high, self._floor_low
        self._step = self._floor_high - self._floor_low
        self._motion = motion if motion is not None else MotionProfileParams()
        self._mode = ElevatorMode.NORMAL
        self._anim = None

    @property
    def mode(self) -> ElevatorMode:
        return self._mode

    def set_mode(self, mode: ElevatorMode) -> None:
        if isinstance(mode, str):
            mode = ElevatorMode(mode)
        elif not isinstance(mode, ElevatorMode):
            mode = ElevatorMode(str(mode))
        self._mode = mode

    def _travel_speed_cap(self) -> float:
        if self._mode == ElevatorMode.INSPECTION:
            return self._motion.v_inspection
        return self._motion.v_nom

    @property
    def prim_path(self) -> str:
        return self._prim_path

    @property
    def travel_axis(self) -> str:
        return self._axis

    @property
    def step(self) -> float:
        return self._step

    @property
    def step_y(self) -> float:
        """Backward-compatible alias (panel used ``step_y`` for the old cube)."""
        return self._step

    @step_y.setter
    def step_y(self, value: float) -> None:
        self._step = max(0.01, float(value))

    @property
    def motion_params(self) -> MotionProfileParams:
        return self._motion

    @property
    def is_moving(self) -> bool:
        return self._anim is not None

    def get_motion_phase(self) -> Optional[str]:
        if not self._anim:
            return None
        return str(self._anim.get("phase"))

    def reset_animation(self) -> None:
        self._anim = None

    def _get_stage(self):
        import omni.usd

        ctx = omni.usd.get_context()
        if not ctx:
            return None
        return ctx.get_stage()

    def _get_translate_op(self, prim):
        from pxr import UsdGeom

        xformable = UsdGeom.Xformable(prim)
        if not xformable:
            return None
        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                return op
        return None

    def _read_translate(self) -> Tuple[Optional[object], Optional[str]]:
        from pxr import Gf

        stage = self._get_stage()
        if not stage:
            return None, "no stage"

        prim = stage.GetPrimAtPath(self._prim_path)
        if not prim or not prim.IsValid():
            return None, f"prim not found: {self._prim_path}"

        op = self._get_translate_op(prim)
        if not op:
            return None, "prim has no xformOp:translate"

        val = op.Get()
        if val is None:
            val = Gf.Vec3d(0, 0, 0)
        return val, None

    def _axis_value(self, translate) -> float:
        return float(translate[self._axis_index])

    def _apply_translate(self, translate) -> Optional[str]:
        from pxr import Usd, UsdGeom

        stage = self._get_stage()
        if not stage:
            return "no stage"

        prim = stage.GetPrimAtPath(self._prim_path)
        if not prim or not prim.IsValid():
            return f"prim not found: {self._prim_path}"

        xformable = UsdGeom.Xformable(prim)
        if not xformable:
            return "prim is not transformable"

        op = self._get_translate_op(prim)
        with Usd.EditContext(stage, stage.GetEditTarget()):
            if op:
                op.Set(translate)
            else:
                xformable.AddTranslateOp().Set(translate)
        return None

    def _current_animated_pos(self) -> Optional[float]:
        if not self._anim:
            translate, err = self._read_translate()
            if err:
                return None
            return self._axis_value(translate)

        anim = self._anim
        if anim["phase"] == "start_delay":
            return float(anim["start"])
        if anim["phase"] == "stop_delay":
            return float(anim["final_end"])
        return float(anim.get("pos", anim["start"]))

    def _approach_and_final(self, start: float, final_end: float) -> Tuple[float, float]:
        """
        Main profile stops ``leveling_distance`` before the floor stop; leveling
        crawls the remainder at ``leveling_speed`` (KDL16-style).
        """
        dist = abs(final_end - start)
        crawl = min(
            max(0.0, self._motion.leveling_distance),
            max(0.0, dist - self._motion.stop_eps),
        )
        if crawl <= 1e-6 or self._motion.leveling_speed <= 1e-6:
            return final_end, final_end
        if final_end > start:
            return final_end - crawl, final_end
        return final_end + crawl, final_end

    def get_state(self) -> dict:
        translate, err = self._read_translate()
        if err:
            return {"error": err}

        pos = self._current_animated_pos()
        if pos is None:
            pos = self._axis_value(translate)

        state = {
            "primPath": self._prim_path,
            "travelAxis": self._axis.upper(),
            "x": float(translate[0]),
            "y": float(translate[1]),
            "z": float(translate[2]),
            "position": float(pos),
            "step": self._step,
            "stepY": self._step,
            "floorLow": self._floor_low,
            "floorHigh": self._floor_high,
            "moving": self.is_moving,
            "mode": self._mode.value,
            "ratedSpeed": self._motion.v_nom,
            "travelSpeedCap": self._travel_speed_cap(),
            "accel": self._motion.accel,
            "levelingSpeed": self._motion.leveling_speed,
        }
        if self._anim:
            state["targetPosition"] = float(self._anim["final_end"])
            state["targetY"] = float(self._anim["final_end"])
            state["motionPhase"] = self._anim.get("phase")
            if self._anim["phase"] == "moving":
                state["velocity"] = float(self._anim.get("vel", 0.0))
                plan = self._anim.get("plan")
                if plan is not None:
                    state["moveDuration"] = float(plan.duration)
                    state["peakSpeed"] = float(plan.peak_speed)
                    state["decelStartPos"] = float(plan.decel_start_pos)
                    state["levelingStartPos"] = float(self._anim.get("end"))
            elif self._anim["phase"] == "leveling":
                state["velocity"] = float(self._anim.get("vel", 0.0))
                state["levelingStartPos"] = float(self._anim.get("end"))
        floor = self.get_current_floor()
        if floor is not None:
            state["currentFloor"] = floor
        return state

    def get_current_floor(self) -> Optional[int]:
        """0 = lower stop, 1 = upper stop (nearest travel-axis stop)."""
        translate, err = self._read_translate()
        if err:
            return None
        pos = self._current_animated_pos()
        if pos is None:
            pos = self._axis_value(translate)
        pos = float(pos)
        d_low = abs(pos - self._floor_low)
        d_high = abs(pos - self._floor_high)
        if d_low <= d_high:
            return 0
        return 1

    def _target_floor(self, direction: int) -> float:
        return self._floor_high if direction > 0 else self._floor_low

    def _at_floor_limit(self, start: float, direction: int) -> bool:
        if direction > 0:
            return start >= self._floor_high - _POS_EPS
        return start <= self._floor_low + _POS_EPS

    def request_move(self, direction: int) -> dict:
        """Move between floor stops: fast profile to approach point, then leveling crawl."""
        if direction not in (-1, 1):
            return {"error": "direction must be -1 or 1"}

        if self._anim:
            start = self._current_animated_pos()
        else:
            translate, err = self._read_translate()
            if err:
                return {"error": err}
            start = self._axis_value(translate)

        if start is None:
            return {"error": "cannot read elevator position"}

        if self._at_floor_limit(start, direction):
            return {"error": "at travel limit"}

        final_end = self._target_floor(direction)
        if abs(final_end - start) < _POS_EPS:
            return {"error": "at travel limit"}

        self._begin_animation(float(start), float(final_end))
        return self.get_state()

    def _begin_animation(self, start: float, final_end: float) -> None:
        approach_end, final_end = self._approach_and_final(start, final_end)
        self._anim = {
            "start": start,
            "end": approach_end,
            "final_end": final_end,
            "pos": start,
            "vel": 0.0,
            "phase": "start_delay",
            "delay_remaining": max(0.0, self._motion.start_delay_sec),
            "plan": None,
            "move_elapsed": 0.0,
            "use_leveling": abs(approach_end - final_end) > self._motion.stop_eps,
        }
        self._write_axis_pos(start)

    def _write_axis_pos(self, pos: float) -> Optional[str]:
        from pxr import Gf

        translate, err = self._read_translate()
        if err:
            return err
        components = [float(translate[0]), float(translate[1]), float(translate[2])]
        components[self._axis_index] = float(pos)
        return self._apply_translate(Gf.Vec3d(*components))

    def _start_move_phase(self) -> None:
        anim = self._anim
        if not anim:
            return
        start = float(anim["start"])
        approach_end = float(anim["end"])
        plan = build_trip_plan(
            start, approach_end, self._motion, v_cap_override=self._travel_speed_cap()
        )
        anim["plan"] = plan
        anim["move_elapsed"] = 0.0
        anim["pos"] = start
        anim["vel"] = 0.0
        anim["phase"] = "moving"

    def _enter_stop_delay(self) -> None:
        anim = self._anim
        if not anim:
            return
        anim["phase"] = "stop_delay"
        anim["delay_remaining"] = max(0.0, self._motion.stop_delay_sec)
        anim["pos"] = float(anim["final_end"])
        anim["vel"] = 0.0
        self._write_axis_pos(float(anim["final_end"]))
        if anim["delay_remaining"] <= 0.0:
            self._anim = None

    def update(self, dt: float) -> bool:
        """Advance animation; returns True when the displayed position changed."""
        if not self._anim:
            return False

        dt = max(0.0, float(dt))
        anim = self._anim
        phase = anim["phase"]

        if phase == "start_delay":
            anim["delay_remaining"] -= dt
            if anim["delay_remaining"] > 0.0:
                return False
            self._start_move_phase()
            return False

        if phase == "moving":
            plan: TripPlan = anim["plan"]
            anim["move_elapsed"] = float(anim.get("move_elapsed", 0.0)) + dt
            pos, vel, finished = sample_trip_plan(plan, anim["move_elapsed"])
            anim["pos"] = pos
            anim["vel"] = vel
            err = self._write_axis_pos(pos)
            if err:
                self._anim = None
                return False
            if not finished:
                return True
            if anim.get("use_leveling"):
                anim["phase"] = "leveling"
                anim["vel"] = 0.0
                return True
            self._enter_stop_delay()
            return True

        if phase == "leveling":
            final_end = float(anim["final_end"])
            pos = float(anim["pos"])
            dist = final_end - pos
            dist_abs = abs(dist)
            eps = self._motion.stop_eps
            if dist_abs <= eps:
                anim["pos"] = final_end
                anim["vel"] = 0.0
                self._write_axis_pos(final_end)
                self._enter_stop_delay()
                return True

            dir_sign = 1.0 if dist > 0.0 else -1.0
            speed = max(1e-6, self._motion.leveling_speed)
            step = min(dist_abs, speed * dt)
            if final_end > anim["start"]:
                pos = min(pos + step, final_end)
            else:
                pos = max(pos - step, final_end)
            anim["pos"] = pos
            anim["vel"] = dir_sign * speed
            err = self._write_axis_pos(pos)
            if err:
                self._anim = None
                return False
            return True

        if phase == "stop_delay":
            anim["delay_remaining"] -= dt
            if anim["delay_remaining"] > 0.0:
                return False
            self._anim = None
            return False

        self._anim = None
        return False

    def move(self, direction: int) -> dict:
        """Backward-compatible alias for ``request_move``."""
        return self.request_move(direction)
