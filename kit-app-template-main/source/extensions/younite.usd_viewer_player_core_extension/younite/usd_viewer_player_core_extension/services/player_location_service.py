from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple


@dataclass(frozen=True)
class PlayerWorldLocation:
    prim_path: str
    pos: Tuple[float, float, float]
    timestamp_s: float


# ── player pose dispatch tuning ─────────────────────────────────────────
# Rate-limit ``playerPose`` dispatch so we don't flood the data channel
# while still feeling responsive to ambient sound placement.
_POSE_DISPATCH_HZ = 20.0
_POSE_MIN_INTERVAL_S = 1.0 / _POSE_DISPATCH_HZ
_POSE_POS_THRESHOLD_CM = 2.0
_POSE_ANGLE_THRESHOLD_COS = math.cos(math.radians(0.5))  # dot-product cutoff


class PlayerLocationService:
    """
    Tracks the player's world-space position (translation) and emits diagnostics when it changes.

    Designed to be driven by `PlayerUpdateLoop` (call `update(dt)` once per frame).

    Additionally dispatches ``playerPose`` events (~20 Hz) containing both the
    player's world position and an orientation basis (forward + up vectors).
    These are consumed by the browser-side ambient sound engine so
    ``PannerNode``s can pan individual emitters around the listener.

    Dispatch is gated on the sound emitter list being non-empty (observed
    via the ``soundEmittersStatus`` event) so we pay zero bandwidth cost
    while the world has no ambient emitters authored.
    """

    def __init__(
        self,
        *,
        get_player_path: Callable[[], Optional[str]],
        min_distance: float = 1.0,
        min_print_interval_s: float = 0.10,
        print_on_change: bool = True,
    ):
        self._get_player_path = get_player_path
        self._min_distance = float(min_distance)
        self._min_print_interval_s = float(min_print_interval_s)
        self._print_on_change = bool(print_on_change)

        self._last_location: Optional[PlayerWorldLocation] = None
        self._last_print_s: float = 0.0
        self._last_stage_id: str = ""

        # ── player-pose dispatch state ──
        self._last_pose_dispatch_s: float = 0.0
        self._last_pose_pos: Optional[Tuple[float, float, float]] = None
        self._last_pose_forward: Optional[Tuple[float, float, float]] = None
        self._has_emitters: bool = False
        self._emitters_sub = None
        self._subscribe_to_emitter_status()

    def stop(self) -> None:
        self.reset()
        if getattr(self, "_emitters_sub", None) is not None:
            try:
                self._emitters_sub = None
            except Exception:
                pass

    def reset(self) -> None:
        self._last_location = None
        self._last_print_s = 0.0
        self._last_stage_id = ""
        self._last_pose_dispatch_s = 0.0
        self._last_pose_pos = None
        self._last_pose_forward = None

    def get_player_world_position(self) -> Optional[Tuple[float, float, float]]:
        loc = self._last_location
        return loc.pos if loc else None

    def get_player_geo_position(self) -> Optional[Tuple[float, float, float]]:
        """Return the player's current position as (latitude, longitude, height) in WGS84.

        Requires GeoCoordinateService to be ready (CesiumGeoreference loaded).
        Returns None if the player position or geo service is unavailable.
        """
        pos = self.get_player_world_position()
        if not pos:
            return None
        try:
            from younite.usd_viewer_stage_core_extension.services.core_services.geo_coordinate_service import get_geo_coordinate_service
            geo = get_geo_coordinate_service()
            if geo:
                return geo.usd_to_latlon(*pos)
        except Exception:
            pass
        return None

    # ── emitter-list gating ─────────────────────────────────────────
    def _subscribe_to_emitter_status(self) -> None:
        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app

            name = "soundEmittersStatus"
            try:
                kit_app.register_event_alias(carb.events.type_from_string(name), name)
            except Exception:
                pass

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _on_status(event):
                try:
                    from younite.messaging_core_extension.message_utils import (
                        normalize_event_payload,
                    )
                    payload = normalize_event_payload(getattr(event, "payload", None) or {})
                    emitters = payload.get("emitters")
                    count = len(emitters) if isinstance(emitters, list) else 0
                    self._has_emitters = count > 0
                except Exception:
                    pass

            self._emitters_sub = ed.observe_event(
                observer_name="younite.player_location/soundEmittersStatus",
                event_name=name,
                on_event=_on_status,
                order=0,
            )
        except Exception:
            self._emitters_sub = None

    def update(self, _dt: float = 0.0) -> None:
        try:
            import omni.usd
            from pxr import Usd, UsdGeom, Gf
        except Exception:
            return

        stage = None
        try:
            stage = omni.usd.get_context().get_stage()
        except Exception:
            stage = None
        if not stage:
            return

        # Reset across stage switches (scene changes).
        try:
            stage_id = str(stage.GetRootLayer().identifier or "")
        except Exception:
            stage_id = ""
        if stage_id != self._last_stage_id:
            self._last_stage_id = stage_id
            self._last_location = None
            self._last_print_s = 0.0
            self._last_pose_pos = None
            self._last_pose_forward = None
            self._last_pose_dispatch_s = 0.0

        player_path = None
        try:
            player_path = self._get_player_path()
        except Exception:
            player_path = None

        if not player_path:
            return

        prim = None
        try:
            prim = stage.GetPrimAtPath(str(player_path))
            if not (prim and prim.IsValid()):
                prim = None
        except Exception:
            prim = None

        if prim is None:
            return

        # World-space transform from USD Xform.
        try:
            cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            m = cache.GetLocalToWorldTransform(prim)
            t = m.ExtractTranslation()
            pos = (float(t[0]), float(t[1]), float(t[2]))
        except Exception:
            return

        now_s = time.time()
        last = self._last_location
        self._last_location = PlayerWorldLocation(prim_path=str(player_path), pos=pos, timestamp_s=now_s)

        # ── playerPose dispatch (gated + throttled) ──
        self._maybe_dispatch_pose(m, pos, now_s, Gf)

        if not self._print_on_change:
            return

        if last is None:
            self._last_print_s = now_s
            return

        dx = pos[0] - last.pos[0]
        dy = pos[1] - last.pos[1]
        dz = pos[2] - last.pos[2]
        dist2 = (dx * dx) + (dy * dy) + (dz * dz)
        min_d = float(self._min_distance)
        if dist2 < (min_d * min_d):
            return

        if (now_s - float(self._last_print_s)) < float(self._min_print_interval_s):
            return

        self._last_print_s = now_s

    # ── playerPose dispatch helpers ─────────────────────────────────
    def _extract_forward_up(self, matrix, Gf) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
        """Pull forward and up vectors from the local-to-world matrix.

        Kit's first-person player prim is Y-up with -Z = forward (USD camera
        convention).  We rotate the basis vectors by the matrix's rotation
        submatrix and renormalise to strip any scale.
        """
        try:
            rot = matrix.ExtractRotation() if hasattr(matrix, "ExtractRotation") else None
            if rot is not None:
                fwd_local = Gf.Vec3d(0.0, 0.0, -1.0)
                up_local = Gf.Vec3d(0.0, 1.0, 0.0)
                fwd = rot.TransformDir(fwd_local)
                up = rot.TransformDir(up_local)
            else:
                # Fallback: transform direction vectors manually (row 0..2 of matrix).
                fwd = matrix.TransformDir(Gf.Vec3d(0.0, 0.0, -1.0))
                up = matrix.TransformDir(Gf.Vec3d(0.0, 1.0, 0.0))
            fx, fy, fz = float(fwd[0]), float(fwd[1]), float(fwd[2])
            ux, uy, uz = float(up[0]), float(up[1]), float(up[2])
            fn = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
            un = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
            return ((fx / fn, fy / fn, fz / fn), (ux / un, uy / un, uz / un))
        except Exception:
            return None

    def _maybe_dispatch_pose(self, matrix, pos: Tuple[float, float, float], now_s: float, Gf) -> None:
        if not self._has_emitters:
            return
        if (now_s - self._last_pose_dispatch_s) < _POSE_MIN_INTERVAL_S:
            return

        basis = self._extract_forward_up(matrix, Gf)
        if basis is None:
            return
        forward, up = basis

        # Threshold gates: skip dispatch if nothing moved / rotated enough.
        if self._last_pose_pos is not None and self._last_pose_forward is not None:
            dpx = pos[0] - self._last_pose_pos[0]
            dpy = pos[1] - self._last_pose_pos[1]
            dpz = pos[2] - self._last_pose_pos[2]
            pos_changed = (dpx * dpx + dpy * dpy + dpz * dpz) >= (_POSE_POS_THRESHOLD_CM * _POSE_POS_THRESHOLD_CM)

            lf = self._last_pose_forward
            dot = forward[0] * lf[0] + forward[1] * lf[1] + forward[2] * lf[2]
            orientation_changed = dot < _POSE_ANGLE_THRESHOLD_COS

            if not pos_changed and not orientation_changed:
                return

        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2
            dispatch_to_events2("playerPose", {
                "pos": [pos[0], pos[1], pos[2]],
                "forward": [forward[0], forward[1], forward[2]],
                "up": [up[0], up[1], up[2]],
                "t": now_s,
            })
            self._last_pose_dispatch_s = now_s
            self._last_pose_pos = pos
            self._last_pose_forward = forward
        except Exception:
            pass
