"""Two-panel door motion (door 1 leads, then both together; decel on final leg)."""

from dataclasses import dataclass
from typing import Optional, Tuple

_POS_EPS = 1e-4
_SYNC_EPS = 0.08
# Last fraction of total travel where speed ramps down into the stop (real doors stay linear until ~here).
_DECEL_FINAL_FRACTION = 0.05
_DECEL_MIN_SPEED = 0.06


@dataclass(frozen=True)
class DoorPairStops:
    door1_closed: float
    door1_middle: float
    door1_open: float
    door2_closed: float
    door2_open: float


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lead_fraction(stops: DoorPairStops) -> float:
    lead = abs(stops.door1_middle - stops.door1_closed)
    together = abs(stops.door1_open - stops.door1_middle)
    total = lead + together
    if total <= 1e-9:
        return 0.5
    return lead / total


def _progress_speed(progress: float, opening: bool, lead_frac: float) -> float:
    """Full speed until the last ~5% of travel, then rapid decel into the stop."""
    del opening, lead_frac
    p = max(0.0, min(1.0, float(progress)))
    decel_start = 1.0 - _DECEL_FINAL_FRACTION
    if p <= decel_start:
        return 1.0
    rem = (p - decel_start) / _DECEL_FINAL_FRACTION
    rem = max(0.0, min(1.0, rem))
    # Steep drop in the last 5% (quartic — stays near 1.0 until rem is high).
    return max(_DECEL_MIN_SPEED, (1.0 - rem) ** 4)


def sample_open(u: float, stops: DoorPairStops, lead_frac: float) -> Tuple[float, float]:
    u = max(0.0, min(1.0, float(u)))
    if u <= lead_frac:
        t = u / lead_frac if lead_frac > 0 else 1.0
        x1 = _lerp(stops.door1_closed, stops.door1_middle, t)
        x2 = stops.door2_closed
    else:
        span = 1.0 - lead_frac
        t = (u - lead_frac) / span if span > 0 else 1.0
        x1 = _lerp(stops.door1_middle, stops.door1_open, t)
        x2 = _lerp(stops.door2_closed, stops.door2_open, t)
    return x1, x2


def sample_close(u: float, stops: DoorPairStops, lead_frac: float) -> Tuple[float, float]:
    u = max(0.0, min(1.0, float(u)))
    if u <= (1.0 - lead_frac):
        span = 1.0 - lead_frac
        t = u / span if span > 0 else 1.0
        x1 = _lerp(stops.door1_open, stops.door1_middle, t)
        x2 = _lerp(stops.door2_open, stops.door2_closed, t)
    else:
        span = lead_frac
        t = (u - (1.0 - lead_frac)) / span if span > 0 else 1.0
        x1 = _lerp(stops.door1_middle, stops.door1_closed, t)
        x2 = stops.door2_closed
    return x1, x2


def is_pair_open(d1: float, d2: float, stops: DoorPairStops, eps: float = _SYNC_EPS) -> bool:
    return (
        abs(d1 - stops.door1_open) < eps
        and abs(d2 - stops.door2_open) < eps
    )


def is_pair_closed(d1: float, d2: float, stops: DoorPairStops, eps: float = _SYNC_EPS) -> bool:
    return (
        abs(d1 - stops.door1_closed) < eps
        and abs(d2 - stops.door2_closed) < eps
    )


class DoorPairController:
    def __init__(
        self,
        door1_path: str,
        door2_path: str,
        stops: DoorPairStops,
        open_duration_sec: float = 1.8,
        close_duration_sec: float = 2.2,
    ):
        self.door1_path = door1_path
        self.door2_path = door2_path
        self.stops = stops
        self.open_duration_sec = max(0.2, float(open_duration_sec))
        self.close_duration_sec = max(0.2, float(close_duration_sec))
        self.lead_fraction = _lead_fraction(stops)
        self._anim = None
        self._is_open = False

    @property
    def is_animating(self) -> bool:
        return self._anim is not None

    @property
    def is_open(self) -> bool:
        return self._is_open

    def _get_stage(self):
        import omni.usd

        ctx = omni.usd.get_context()
        return ctx.get_stage() if ctx else None

    def _read_translate(self, prim_path: str) -> Tuple[Optional[object], Optional[str]]:
        from pxr import Gf

        stage = self._get_stage()
        if not stage:
            return None, "no stage"
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return None, f"prim not found: {prim_path}"
        from pxr import UsdGeom

        xformable = UsdGeom.Xformable(prim)
        if not xformable:
            return None, "not transformable"
        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                val = op.Get()
                if val is None:
                    val = Gf.Vec3d(0, 0, 0)
                return val, None
        return None, "no xformOp:translate"

    def _write_translate_x(self, prim_path: str, x: float) -> Optional[str]:
        from pxr import Gf, Usd, UsdGeom

        translate, err = self._read_translate(prim_path)
        if err:
            return err
        stage = self._get_stage()
        if not stage:
            return "no stage"
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return f"prim not found: {prim_path}"

        new_t = Gf.Vec3d(float(x), float(translate[1]), float(translate[2]))
        xformable = UsdGeom.Xformable(prim)
        op = None
        for candidate in xformable.GetOrderedXformOps():
            if candidate.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                op = candidate
                break
        with Usd.EditContext(stage, stage.GetEditTarget()):
            if op:
                op.Set(new_t)
            else:
                xformable.AddTranslateOp().Set(new_t)
        return None

    def _set_pair_x(self, x1: float, x2: float) -> Optional[str]:
        err = self._write_translate_x(self.door1_path, x1)
        if err:
            return err
        return self._write_translate_x(self.door2_path, x2)

    def request_open(self) -> dict:
        if self._anim:
            return {"error": "doors already moving"}
        if self._is_open:
            return {"error": "doors already open"}
        self._anim = {
            "opening": True,
            "progress": 0.0,
            "duration": self.open_duration_sec,
        }
        return {"ok": True, "action": "open"}

    def request_close(self) -> dict:
        if self._anim:
            return {"error": "doors already moving"}
        if not self._is_open:
            return {"error": "doors already closed"}
        self._anim = {
            "opening": False,
            "progress": 0.0,
            "duration": self.close_duration_sec,
        }
        return {"ok": True, "action": "close"}

    def reset_animation(self) -> None:
        self._anim = None

    def sync_open_state_from_stage(self) -> None:
        t1, e1 = self._read_translate(self.door1_path)
        t2, e2 = self._read_translate(self.door2_path)
        if e1 or e2:
            return
        if is_pair_open(float(t1[0]), float(t2[0]), self.stops):
            self._is_open = True
        elif is_pair_closed(float(t1[0]), float(t2[0]), self.stops):
            self._is_open = False

    def update(self, dt: float) -> bool:
        if not self._anim:
            return False

        anim = self._anim
        duration = max(1e-9, float(anim["duration"]))
        progress = float(anim["progress"])

        if progress < 1.0:
            speed = _progress_speed(progress, bool(anim["opening"]), self.lead_fraction)
            progress = min(1.0, progress + (max(0.0, float(dt)) / duration) * speed)
            anim["progress"] = progress

        if anim["opening"]:
            x1, x2 = sample_open(progress, self.stops, self.lead_fraction)
        else:
            x1, x2 = sample_close(progress, self.stops, self.lead_fraction)

        self._set_pair_x(x1, x2)

        if progress < 1.0:
            return True

        self._is_open = bool(anim["opening"])
        self._anim = None
        return True

    def get_state(self) -> dict:
        t1, e1 = self._read_translate(self.door1_path)
        t2, e2 = self._read_translate(self.door2_path)
        if e1 or e2:
            return {"error": e1 or e2}
        return {
            "door1X": float(t1[0]),
            "door2X": float(t2[0]),
            "open": self._is_open,
            "animating": self.is_animating,
        }
