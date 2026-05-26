from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .ease_helpers import ease_scale_remaining, ease_scale_traveled


# Path-class transition logging. Flip to False to silence the per-segment
# console prints (the `playerPathClassChange` event is still dispatched
# either way — the log is purely a developer convenience).
_LOG_PATH_CLASS: bool = True


class PointClickAutoMover:
    """
    Point&click waypoint follower (player only).

    - Consumes normalized `navigationStateSet` + `navmeshRouteWaypoints` payloads from the orchestrator.
    - On update(dt), walks along the navmesh polyline and smoothly rotates camera yaw via look-ahead.

    Anti-jitter / comfort features:
      1. Look-ahead direction (camera aims further along the path, not just the next point)
      2. Exponential smoothing on camera target yaw (low-pass filter)
      3. Asymmetric ease on walk speed only (~120 cm ease-in, ~450 cm ease-out, XZ)
    """

    # --- Tuning constants (class-level so they're easy to tweak) ---
    LOOK_AHEAD_DIST: float = 800.0      # How far ahead to aim the camera (stage units)
    YAW_SMOOTH_FACTOR: float = 0.095    # Low-pass on look-ahead target (lower = smoother heading changes)
    YAW_TURN_EASE_ZONE_DEG: float = 44.0  # Smoothstep ease-in/out on turn rate (not constant-speed snap)
    YAW_TURN_EASE_MIN_SCALE: float = 0.34
    # Asymmetric ease along the route (XZ distance). Ramps between EASE_MIN_SPEED_SCALE
    # and full speed; ease-in is shorter (snappy start), ease-out longer (soft stop).
    EASE_IN_ZONE_DISTANCE_CM: float = 120.0
    EASE_OUT_ZONE_DISTANCE_CM: float = 450.0
    EASE_MIN_SPEED_SCALE: float = 0.05
    # Tighter snap on the last waypoint so ease-out can run the full deceleration ramp
    # (default arrive_threshold would stop ~50 cm early and feel abrupt).
    FINAL_ARRIVE_THRESHOLD_CM: float = 10.0

    def __init__(
        self,
        *,
        route_id: str = "player",
        arrive_threshold: float = 50.0,
        turn_rate_deg_per_s: float = 124.0,
        get_stage: Callable[[], Any],
        get_player_path: Callable[[], str],
        get_camera_path: Callable[[], str],
        get_speed_multiplier: Callable[[], float],
        get_movement_controller: Callable[[], Any],
        get_touch_look: Optional[Callable[[], Any]] = None,
        get_is_face_turn_active: Optional[Callable[[], bool]] = None,
        on_complete: Optional[Callable[[str, str], None]] = None,
    ):
        self._enabled = False  # pointClick mode
        self._auto_move = False
        self._active = False
        self._route_id = route_id
        self._arrive_threshold = float(arrive_threshold)
        self._turn_rate = float(turn_rate_deg_per_s)

        self._get_stage = get_stage
        self._get_player_path = get_player_path
        self._get_camera_path = get_camera_path
        self._get_speed_multiplier = get_speed_multiplier
        self._get_movement_controller = get_movement_controller
        self._get_touch_look = get_touch_look
        self._get_is_face_turn_active = get_is_face_turn_active
        self._on_complete = on_complete

        self._waypoints: List[Tuple[float, float, float]] = []
        # Per-segment speed multiplier. ``len(_segment_speeds) == len(_waypoints) - 1``.
        # ``_segment_speeds[i]`` scales the base move speed for the segment
        # ``waypoints[i] → waypoints[i+1]``. Defaults to 1.0 for every segment
        # when the producer omits `segmentSpeeds`. Used by the OSM bridge to
        # speed up the long entrance ↔ pin crossings (set by
        # `feature_commands_service` when priming the OSM polyline).
        self._segment_speeds: List[float] = []
        # Per-segment path classes (``"navmesh"`` / ``"pedestrian"`` /
        # ``"bridge"`` / ...). ``len(_segment_classes) == len(_waypoints) - 1``
        # or empty when the producer omits it. Drives the transition log
        # + ``playerPathClassChange`` event below.
        self._segment_classes: List[str] = []
        self._last_class: Optional[str] = None
        self._wp_idx = 0
        self._last_updated_ms = int(time.time() * 1000)
        self._smoothed_yaw: float | None = None
        self._yaw_turn_initial_remaining: float = 0.0
        self._user_looking: bool = False  # True while user is swiping the camera
        self._arrival_aabb_min: Optional[Tuple[float, float, float]] = None
        self._arrival_aabb_max: Optional[Tuple[float, float, float]] = None
        self._route_total_len_xz: float = 0.0

    def set_is_face_turn_active(self, getter: Optional[Callable[[], bool]]) -> None:
        """When the nav orchestrator is easing yaw, auto-mover must not write camera yaw."""
        self._get_is_face_turn_active = getter

    def start(self) -> None:
        # Subscription ownership is in NavigationOrchestratorService.
        return

    def stop(self, *, _reason: str = "cancelled") -> None:
        was_active = self._active
        rid = self._route_id
        self._active = False
        self._waypoints = []
        self._segment_speeds = []
        self._segment_classes = []
        self._last_class = None
        self._wp_idx = 0
        self._smoothed_yaw = None
        self._yaw_turn_initial_remaining = 0.0
        self._arrival_aabb_min = None
        self._arrival_aabb_max = None
        self._route_total_len_xz = 0.0
        # Do NOT force-enable manual input here; that is controlled by navigation state / UI.
        if was_active and self._on_complete:
            try:
                self._on_complete(rid, _reason)
            except Exception:
                pass

    def shutdown(self) -> None:
        self._on_complete = None
        self.stop()

    def on_navigation_state(self, payload: Dict[str, Any]) -> None:
        """
        Consume normalized `navigationStateSet` payload from orchestrator.
        Keys used: movementMode, autoMove, routeId.

        Resume semantics: when ``autoMove`` flips False→True and we still
        have cached waypoints from a previous route dispatch, reactivate
        immediately without waiting for a fresh ``navmeshRouteWaypoints``
        event. The orchestrator's ``_apply_state`` will re-dispatch
        ``navmeshRouteCalculate`` on the same tick, which keeps the
        route engine alive and produces a fresh recompute as a follow
        up — but the cached fast-path means there's no perceptible lag
        between Play and the player starting to move.
        """
        try:
            if "movementMode" in payload:
                self._enabled = (str(payload.get("movementMode") or "") == "pointClick")
                if not self._enabled:
                    self.stop()
            if "autoMove" in payload:
                was_auto = bool(self._auto_move)
                self._auto_move = bool(payload.get("autoMove"))
                if not self._auto_move:
                    self.stop()
                elif (
                    not was_auto
                    and self._enabled
                    and self._waypoints
                    and int(self._wp_idx) < len(self._waypoints)
                ):
                    # Fresh activation — force the next update() to re-seed
                    # the look-ahead smoother from the current camera /
                    # player pose. Without this, a stale ``_smoothed_yaw``
                    # from an earlier leg (or a user swipe that happened
                    # while paused) can freeze the camera on the initial
                    # direction and the character visually walks sideways
                    # until the user touches the viewport and releases.
                    self._active = True
                    self._smoothed_yaw = None
                    self._user_looking = False
            if "routeId" in payload:
                rid = str(payload.get("routeId") or "").strip()
                if rid:
                    self._route_id = rid
            self._last_updated_ms = int(time.time() * 1000)
        except Exception:
            pass

    def on_route_waypoints(self, payload: Dict[str, Any]) -> None:
        """
        Consume normalized `navmeshRouteWaypoints` payload from orchestrator.
        Expected payload: { routeId, success, points } where points is list of vec3.
        """
        try:
            rid = str(payload.get("routeId") or "")
            if rid != str(self._route_id):
                return
            if not bool(payload.get("success", False)):
                err = str(payload.get("error") or "")
                # Remaining polyline distance < threshold (see navmesh route periodic measure);
                # not the same as reaching the last navmesh vertex — seat snap must still run.
                if err == "lightweight_arrival":
                    self.stop(_reason="arrived")
                else:
                    # Failed click, recalculating, manual stop ("stopped"), etc.
                    self._arrival_aabb_min = None
                    self._arrival_aabb_max = None
                    self.stop(_reason="route_failed")
                return
            pts = payload.get("points")
            if not isinstance(pts, list) or len(pts) < 2:
                return
            waypoints: List[Tuple[float, float, float]] = []
            for p in pts:
                if isinstance(p, (list, tuple)) and len(p) >= 3:
                    waypoints.append((float(p[0]), float(p[1]), float(p[2])))
            if len(waypoints) < 2:
                return

            # Preserve ``_wp_idx`` when the new dispatch is functionally
            # the same path we're already walking. The Play-resume kick
            # (see ``on_navigation_state``) plus the route engine's
            # periodic recalc both re-dispatch waypoints frequently, and
            # naively resetting ``_wp_idx`` to 0 every time would yank
            # the player backward to the start of an in-progress walk.
            # Match heuristic: same vertex count + endpoints within
            # arrive_threshold. Anything else is treated as a fresh
            # path.
            same_path = (
                bool(self._waypoints)
                and len(self._waypoints) == len(waypoints)
                and self._dist_xz(self._waypoints[0], waypoints[0]) <= float(self._arrive_threshold)
                and self._dist_xz(self._waypoints[-1], waypoints[-1]) <= float(self._arrive_threshold)
            )

            self._waypoints = waypoints
            if not same_path or self._route_total_len_xz <= 1e-6:
                self._route_total_len_xz = self._polyline_length_xz(waypoints)

            # Optional per-segment speed multipliers. Length must match
            # `len(waypoints) - 1`; otherwise we drop them and default to
            # 1.0 everywhere (silently — bad data shouldn't break walking).
            seg_speeds_raw = payload.get("segmentSpeeds")
            seg_speeds: List[float] = []
            if isinstance(seg_speeds_raw, (list, tuple)):
                expected = len(waypoints) - 1
                if len(seg_speeds_raw) == expected:
                    try:
                        seg_speeds = [max(0.01, float(s)) for s in seg_speeds_raw]
                    except (TypeError, ValueError):
                        seg_speeds = []
            self._segment_speeds = seg_speeds

            # Optional per-segment path classes — parallel to segmentSpeeds.
            # Same length contract; mismatches silently drop the table so
            # missing data never breaks playback (the transition detector
            # below just no-ops when the table is empty).
            seg_classes_raw = payload.get("segmentClasses")
            seg_classes: List[str] = []
            if isinstance(seg_classes_raw, (list, tuple)):
                expected = len(waypoints) - 1
                if len(seg_classes_raw) == expected:
                    seg_classes = [str(c or "") for c in seg_classes_raw]
            self._segment_classes = seg_classes

            mn_raw = payload.get("arrivalAabbMin")
            mx_raw = payload.get("arrivalAabbMax")
            if (
                isinstance(mn_raw, (list, tuple))
                and isinstance(mx_raw, (list, tuple))
                and len(mn_raw) >= 3
                and len(mx_raw) >= 3
            ):
                try:
                    self._arrival_aabb_min = (
                        float(mn_raw[0]),
                        float(mn_raw[1]),
                        float(mn_raw[2]),
                    )
                    self._arrival_aabb_max = (
                        float(mx_raw[0]),
                        float(mx_raw[1]),
                        float(mx_raw[2]),
                    )
                except (TypeError, ValueError):
                    self._arrival_aabb_min = None
                    self._arrival_aabb_max = None
            else:
                self._arrival_aabb_min = None
                self._arrival_aabb_max = None

            if not same_path:
                self._wp_idx = 0
                self._smoothed_yaw = None  # re-seed from live yaw on next update
                self._yaw_turn_initial_remaining = 0.0
                self._last_class = None  # re-emit initial class on first tick
            else:
                # Clamp existing index defensively (length matches by
                # construction here, but keep the guard).
                if int(self._wp_idx) >= len(waypoints):
                    self._wp_idx = max(0, len(waypoints) - 1)
            if self._enabled and self._auto_move:
                # Same reason as the fast-path in ``on_navigation_state``:
                # if this dispatch is what activates the mover (``_active``
                # was False until now), drop any stale smoother state so
                # the first frame picks up the live look-ahead direction
                # instead of whatever leftover yaw we were holding from a
                # previous route or pause window.
                was_active = bool(self._active)
                self._active = True
                if not was_active:
                    self._smoothed_yaw = None
                    self._user_looking = False
                # Do NOT disable manual input; point&click auto-move should coexist with WASD.
        except Exception:
            pass

    def is_active(self) -> bool:
        return bool(self._active)

    def should_block_manual_input(self) -> bool:
        """Block only while an auto-move path is actively running (non-idle)."""
        try:
            return bool(self._active and self._waypoints and (int(self._wp_idx) < len(self._waypoints)))
        except Exception:
            return bool(self._active)

    # ------------------------------------------------------------------
    # Helpers used by update()
    # ------------------------------------------------------------------

    @staticmethod
    def _dist_xz(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        dx = a[0] - b[0]
        dz = a[2] - b[2]
        return math.sqrt(dx * dx + dz * dz)

    def _polyline_length_xz(self, waypoints: List[Tuple[float, float, float]]) -> float:
        total = 0.0
        for i in range(1, len(waypoints)):
            total += self._dist_xz(waypoints[i - 1], waypoints[i])
        return total

    def _traveled_xz(
        self,
        pos_x: float,
        pos_z: float,
        idx: int,
    ) -> float:
        """XZ distance along the polyline from the first waypoint to *pos*."""
        wps = self._waypoints
        if len(wps) < 2:
            return 0.0
        idx = max(0, min(int(idx), len(wps)))
        traveled = 0.0
        for i in range(1, idx):
            traveled += self._dist_xz(wps[i - 1], wps[i])
        if idx >= 1:
            seg_start = wps[idx - 1]
            traveled += self._dist_xz(
                seg_start,
                (float(pos_x), float(seg_start[1]), float(pos_z)),
            )
        return traveled

    def _arrive_threshold_for(self, waypoint_idx: int) -> float:
        """Intermediate waypoints use the normal threshold; the last uses a tight finish."""
        if len(self._waypoints) >= 2 and int(waypoint_idx) >= len(self._waypoints) - 1:
            return float(self.FINAL_ARRIVE_THRESHOLD_CM)
        return float(self._arrive_threshold)

    def _ease_speed_scale(self, traveled_xz: float, total_xz: float) -> float:
        """
        Ease-in at route start and ease-out near the end (smoothstep on XZ distance).
        Uses separate ramp lengths for acceleration vs deceleration.
        Returns a multiplier in [EASE_MIN_SPEED_SCALE, 1.0] applied to this frame's walk budget.
        """
        return ease_scale_traveled(
            traveled_xz,
            total_xz,
            zone_in=self.EASE_IN_ZONE_DISTANCE_CM,
            zone_out=self.EASE_OUT_ZONE_DISTANCE_CM,
            min_scale=self.EASE_MIN_SPEED_SCALE,
            cap_out_frac=0.5,
        )

    def _look_ahead_direction(
        self,
        cur: Tuple[float, float, float],
        start_idx: int,
    ) -> Tuple[float, float]:
        """
        Compute a smooth look-ahead direction (XZ) by walking *LOOK_AHEAD_DIST*
        along the remaining path from the player's current position.

        Returns (dir_x, dir_z) — a unit vector on the XZ plane, or the
        direction to the immediate waypoint if the path is too short.
        """
        wps = self._waypoints
        budget = self.LOOK_AHEAD_DIST
        # Start from current position toward the first upcoming waypoint
        prev = cur
        target = wps[start_idx]
        for i in range(start_idx, len(wps)):
            seg_len = self._dist_xz(prev, wps[i])
            if seg_len <= 1e-6:
                prev = wps[i]
                continue
            if budget <= seg_len:
                # Interpolate within this segment
                t = budget / seg_len
                target = (
                    prev[0] + (wps[i][0] - prev[0]) * t,
                    prev[1] + (wps[i][1] - prev[1]) * t,
                    prev[2] + (wps[i][2] - prev[2]) * t,
                )
                break
            budget -= seg_len
            prev = wps[i]
            target = wps[i]

        dx = target[0] - cur[0]
        dz = target[2] - cur[2]
        mag = math.sqrt(dx * dx + dz * dz)
        if mag < 1e-6:
            return 0.0, -1.0
        return dx / mag, dz / mag

    # ------------------------------------------------------------------
    # Path-class transition event
    # ------------------------------------------------------------------

    def _emit_path_class_change(
        self, prev: Optional[str], nxt: str, seg_idx: int,
    ) -> None:
        """Log + dispatch a ``playerPathClassChange`` event.

        Best-effort: the Events 2.0 dispatcher may not be loaded during
        early-startup ticks; silently swallow import errors so a missing
        messaging extension never breaks locomotion.
        """
        total = len(self._segment_classes)
        if _LOG_PATH_CLASS:
            print(
                f"[PathClass] {prev} → {nxt} "
                f"(seg {seg_idx}/{total}, route={self._route_id})"
            )
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
                register_outbound_events,
            )
        except Exception:
            return
        try:
            register_outbound_events(["playerPathClassChange"])
            dispatch_to_events2(
                "playerPathClassChange",
                {
                    "prev": prev,
                    "next": nxt,
                    "segIdx": seg_idx,
                    "routeId": self._route_id,
                },
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Main per-frame update
    # ------------------------------------------------------------------

    def update(self, dt: float) -> bool:
        if not self._active or not self._waypoints:
            return False
        try:
            stage = self._get_stage()
            if not stage:
                return True

            from pxr import UsdGeom, Gf, Usd

            player_path = self._get_player_path() or "/World/PlayerCharacter"
            player_prim = stage.GetPrimAtPath(str(player_path))
            if not (player_prim and player_prim.IsValid()):
                return True

            xf = UsdGeom.Xformable(player_prim)
            m = xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            pos = m.ExtractTranslation() if hasattr(m, "ExtractTranslation") else Gf.Vec3d(m[3][0], m[3][1], m[3][2])
            cur = (float(pos[0]), float(pos[1]), float(pos[2]))

            # Early completion: world AABB at path end (matches navmesh route engine).
            if (
                self._arrival_aabb_min is not None
                and self._arrival_aabb_max is not None
                and len(self._waypoints) >= 2
                and int(self._wp_idx) >= max(0, len(self._waypoints) - 2)
            ):
                mn, mx = self._arrival_aabb_min, self._arrival_aabb_max
                if (
                    mn[0] <= cur[0] <= mx[0]
                    and mn[1] <= cur[1] <= mx[1]
                    and mn[2] <= cur[2] <= mx[2]
                ):
                    lw = self._waypoints[-1]
                    tr_op = xf.GetTranslateOp()
                    if not tr_op:
                        tr_op = xf.AddTranslateOp()
                    tr_op.Set(Gf.Vec3d(float(cur[0]), float(lw[1]), float(cur[2])))
                    self.stop(_reason="arrived")
                    return True

            # --- Consume movement budget across multiple waypoints ---
            # NavMesh paths can have many closely-spaced points.  Instead of
            # advancing one waypoint per frame (which caps speed at
            # waypoint_spacing * fps), we walk along the polyline consuming
            # the full distance budget for this frame.

            idx = int(self._wp_idx)
            pos_x, pos_y, pos_z = cur[0], cur[1], cur[2]

            # Advance past the current target if we've reached it (one at a
            # time to avoid cutting corners through walls).  Snap to the
            # reached waypoint so the budget walk starts ON the polyline
            # instead of taking a straight-line shortcut through geometry.
            # Y is snapped too so the next segment's height interpolation
            # starts from the waypoint's Y (not the player's stale Y).
            if idx < len(self._waypoints) and self._dist_xz(
                cur, self._waypoints[idx]
            ) <= self._arrive_threshold_for(idx):
                pos_x = self._waypoints[idx][0]
                pos_y = self._waypoints[idx][1]
                pos_z = self._waypoints[idx][2]
                idx += 1
            if idx >= len(self._waypoints):
                # Move prim to the reached polyline end before on_complete; otherwise we can
                # "arrive" within threshold while the player is still short (especially on
                # the final segment), and the seat snap fights stale transforms.
                if self._waypoints:
                    lw = self._waypoints[-1]
                    tr_op = xf.GetTranslateOp()
                    if not tr_op:
                        tr_op = xf.AddTranslateOp()
                    tr_op.Set(Gf.Vec3d(float(pos_x), float(lw[1]), float(pos_z)))
                self.stop(_reason="arrived")
                return True

            base_speed = 300.0 * float(self._get_speed_multiplier() or 1.0)
            # Time-budget walk (instead of distance-budget) so per-segment
            # speed multipliers compose correctly when the budget spans
            # multiple segments — each segment consumes
            # ``seg_len / (base_speed * seg_mult)`` of the budget.
            traveled_xz = self._traveled_xz(pos_x, pos_z, idx)
            total_xz = float(self._route_total_len_xz)
            if total_xz <= 1e-6 and len(self._waypoints) >= 2:
                total_xz = self._polyline_length_xz(self._waypoints)
                self._route_total_len_xz = total_xz
            ease_scale = self._ease_speed_scale(traveled_xz, total_xz)
            time_budget = float(dt) * ease_scale
            seg_speeds = self._segment_speeds

            while time_budget > 1e-6 and idx < len(self._waypoints):
                tgt = self._waypoints[idx]
                seg_dx = tgt[0] - pos_x
                seg_dy = tgt[1] - pos_y
                seg_dz = tgt[2] - pos_z
                # Distance is measured on XZ only — Y is driven by the
                # polyline's vertical profile (terrain, indoor floors, OSM
                # node elevation), not player movement. Otherwise a steep
                # segment would count as "longer" and slow the walk.
                seg_len = math.sqrt(seg_dx * seg_dx + seg_dz * seg_dz)

                if seg_len < 1e-6:
                    # Already at this waypoint (XZ), advance. Sync Y so a
                    # pure-Y waypoint difference doesn't leave the player
                    # floating above / below the next segment start.
                    pos_y = tgt[1]
                    idx += 1
                    continue

                # Segment ``idx-1 → idx`` uses ``seg_speeds[idx-1]``. Falls
                # back to 1.0 when no speed table was supplied or when we're
                # mopping up from an arbitrary spawn position before idx 1.
                seg_idx = max(0, idx - 1)
                seg_mult = (
                    seg_speeds[seg_idx]
                    if seg_speeds and seg_idx < len(seg_speeds)
                    else 1.0
                )
                seg_speed = base_speed * seg_mult
                if seg_speed <= 1e-6:
                    # Defensive: a zero-speed segment would deadlock the loop.
                    idx += 1
                    continue
                time_to_complete = seg_len / seg_speed

                if time_budget >= time_to_complete:
                    pos_x = tgt[0]
                    pos_y = tgt[1]
                    pos_z = tgt[2]
                    time_budget -= time_to_complete
                    idx += 1
                else:
                    t = time_budget / time_to_complete
                    pos_x += seg_dx * t
                    pos_y += seg_dy * t
                    pos_z += seg_dz * t
                    time_budget = 0.0

            self._wp_idx = idx

            # Path-class transition detection. The segment the player is
            # currently traversing is ``idx - 1`` (clamped to 0 for the
            # pre-first-waypoint mop-up). Fires once per change including
            # the initial class on route start — ``_last_class`` is reset
            # to ``None`` in ``on_route_waypoints`` / ``stop``.
            if self._segment_classes:
                seg_i = max(0, min(idx - 1, len(self._segment_classes) - 1))
                cls = self._segment_classes[seg_i] or ""
                if cls and cls != self._last_class:
                    self._emit_path_class_change(self._last_class, cls, seg_i)
                    self._last_class = cls

            if idx >= len(self._waypoints):
                # Arrived at final waypoint. Do not apply tr_op.Set below: on_complete
                # (e.g. seat_nav) snaps to lookup/teleport XYZ; polyline last point
                # differs by approach and would overwrite that snap.
                self.stop(_reason="arrived")
                return True

            # Track the camera target (for yaw look-ahead). Y is driven by
            # the interpolated ``pos_y`` above — lifting it straight from
            # the next waypoint caused a visible ground-snap whenever the
            # polyline crossed a height change (OSM terrain, navmesh→OSM
            # bridge), because the Y jumped a full segment ahead of the XZ
            # motion instead of gliding with it.
            cam_target_idx = min(idx, len(self._waypoints) - 1)

            # --- Camera yaw: look-ahead + exponential smoothing ---
            # If the user is swiping (hold+drag), let them control the camera
            # freely.  When the swipe ends, smoothly transition back to the
            # path's look-ahead direction.
            touch_active = False
            try:
                tl = self._get_touch_look() if self._get_touch_look else None
                if tl and hasattr(tl, "is_active"):
                    touch_active = bool(tl.is_active())
            except Exception:
                pass

            face_turn_active = False
            try:
                gf = self._get_is_face_turn_active
                if gf:
                    face_turn_active = bool(gf())
            except Exception:
                face_turn_active = False

            if touch_active:
                # User is swiping — mark that we need to re-acquire the
                # heading smoothly once the swipe ends.
                self._user_looking = True
            elif not face_turn_active:
                try:
                    cam_path = self._get_camera_path()
                    cam_prim = stage.GetPrimAtPath(str(cam_path)) if cam_path else None
                    if cam_prim and cam_prim.IsValid():
                        cam_xf = UsdGeom.Xformable(cam_prim)
                        rot_op = cam_xf.GetRotateXYZOp() or cam_xf.AddRotateXYZOp()
                        cur_rot = rot_op.Get() or Gf.Vec3d(0.0, 0.0, 0.0)
                        cur_pitch = float(cur_rot[0])
                        cur_yaw = float(cur_rot[1])
                        cur_roll = float(cur_rot[2])

                        # If user just released a swipe, re-seed the smoother
                        # from wherever the camera is now so the transition is
                        # gradual, not a snap.
                        if self._user_looking:
                            self._smoothed_yaw = None
                            self._user_looking = False

                        # Resolve parent (capsule) yaw so target is in camera-local space.
                        parent_yaw = 0.0
                        try:
                            _p_rot = xf.GetRotateXYZOp()
                            if _p_rot and _p_rot.Get():
                                parent_yaw = float(_p_rot.Get()[1])
                            else:
                                _p_rot = xf.GetRotateYXZOp()
                                if _p_rot and _p_rot.Get():
                                    parent_yaw = float(_p_rot.Get()[0])
                        except Exception:
                            pass

                        # Look-ahead: aim at a point further along the path
                        new_cur = (pos_x, pos_y, pos_z)
                        la_x, la_z = self._look_ahead_direction(new_cur, cam_target_idx)

                        # World-space yaw toward look-ahead point, converted to camera-local.
                        raw_target_yaw = math.degrees(math.atan2(-la_x, -la_z)) - parent_yaw

                        # Low-pass the look-ahead target; seed from current yaw
                        # on a new path so heading does not snap on click.
                        if self._smoothed_yaw is None:
                            self._smoothed_yaw = cur_yaw
                            to_raw = (raw_target_yaw - cur_yaw + 180.0) % 360.0 - 180.0
                            self._yaw_turn_initial_remaining = max(abs(to_raw), 1.0)
                        else:
                            sm_delta = (raw_target_yaw - self._smoothed_yaw + 180.0) % 360.0 - 180.0
                            self._smoothed_yaw += sm_delta * self.YAW_SMOOTH_FACTOR

                        target_yaw = self._smoothed_yaw

                        # Rate-limited rotation with angular ease-in/out
                        delta = (target_yaw - cur_yaw + 180.0) % 360.0 - 180.0
                        if self._yaw_turn_initial_remaining <= 1e-6:
                            self._yaw_turn_initial_remaining = max(abs(delta), 1.0)
                        turn_ease = ease_scale_remaining(
                            abs(delta),
                            self._yaw_turn_initial_remaining,
                            zone=self.YAW_TURN_EASE_ZONE_DEG,
                            min_scale=self.YAW_TURN_EASE_MIN_SCALE,
                        )
                        max_step = float(self._turn_rate) * float(dt) * turn_ease
                        if abs(delta) > max_step:
                            delta = max_step if delta > 0.0 else -max_step
                        new_yaw = cur_yaw + delta
                        rot_op.Set(Gf.Vec3d(cur_pitch, float(new_yaw), cur_roll))

                        mc = self._get_movement_controller()
                        if mc and hasattr(mc, "set_view_angles"):
                            try:
                                mc.set_view_angles(float(new_yaw), cur_pitch)
                            except Exception:
                                pass
                except Exception:
                    pass

            # Apply final position. ``pos_y`` is the per-frame interpolated
            # height (see time-budget loop) — not the target waypoint's Y,
            # which would snap the player's head at every segment boundary.
            tr_op = xf.GetTranslateOp()
            if not tr_op:
                tr_op = xf.AddTranslateOp()
            tr_op.Set(Gf.Vec3d(float(pos_x), float(pos_y), float(pos_z)))
            return True
        except Exception:
            return True

