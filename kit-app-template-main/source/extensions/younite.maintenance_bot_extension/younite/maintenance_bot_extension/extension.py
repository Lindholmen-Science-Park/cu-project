"""
Maintenance Bot Extension — Incident Orchestrator

Spawns maintenance bot prims at predefined spawn points and orchestrates them
to resolve incidents. Bots are dispatched by priority (highest severity first)
and proximity (NavMesh travel time estimation). If a busy bot would reach a new
incident faster after finishing its current task than the best idle bot, the
assignment is deferred so the busy bot can handle it sequentially.

Events listened to:
  maintenanceBotSpawn       {}                — create bots at spawn points
  maintenanceBotDespawn     {}                — remove all bots and reset
  incidentAdded             { incidentPath, position, severity, status }
  incidentRemoved           { incidentPath }  — confirmation prim is gone
  incidentsCleared          { count }         — all incidents removed
  navmeshRouteWaypoints     { routeId, success, points }

Events dispatched:
  maintenanceBotStatus          { active, count }
  maintenanceBotIncidentUpdate  { botId, incidentId, severity, status, action, eta }
"""

from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import omni.ext

from .bot_mover import BotMover

LOG_TAG = "[maintenance_bot]"
SPAWN_POINT_PREFIX = "/World/maintenance_bot_spawn_"
BOT_PRIM_PREFIX = "/World/MaintenanceBot_"
MODEL_RELATIVE_PATH = "Assets/Maintenance bots/maintenance_bot.usda"
ROUTE_ID_PREFIX = "mbot_"
BOT_SPEED = 200.0  # cm/s (stage units per second)
RESOLVE_TIME_MIN = 5.0
RESOLVE_TIME_MAX = 15.0
RESOLVE_TIME_AVG = (RESOLVE_TIME_MIN + RESOLVE_TIME_MAX) / 2.0

Vec3 = Tuple[float, float, float]


@dataclass
class BotRecord:
    bot_id: str
    prim_path: str
    spawn_pos: Vec3
    state: str = "idle"  # idle | en_route | resolving | returning
    assigned_incident: Optional[str] = None
    mover: BotMover = field(default=None)  # type: ignore[assignment]
    resolve_timer: float = 0.0
    eta_seconds: float = 0.0

    def __post_init__(self):
        if self.mover is None:
            self.mover = BotMover(bot_id=self.bot_id, speed=BOT_SPEED)


@dataclass
class IncidentRecord:
    incident_id: str
    incident_path: str
    position: Vec3
    severity: int
    status: str = "reported"  # reported | resolving | done
    assigned_bot: Optional[str] = None


class MaintenanceBotExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs: list = []
        self._active = False
        self._bots: Dict[str, BotRecord] = {}
        self._incidents: Dict[str, IncidentRecord] = {}
        self._ticking = False
        self._update_sub = None
        self._dispatch = None
        self._rebake_pending = False

        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
                normalize_event_payload,
            )

            self._dispatch = dispatch_to_events2
            ed = carb.eventdispatcher.get_eventdispatcher()

            event_names = [
                "maintenanceBotSpawn", "maintenanceBotDespawn", "maintenanceBotStatus",
                "maintenanceBotIncidentUpdate",
                "incidentAdded", "incidentRemoved", "incidentsCleared",
                "navmeshRouteWaypoints", "incidentRemove",
            ]
            for name in event_names:
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass

            def _observe(event_name, handler, *, order=0):
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.maintenance_bot_extension/{event_name}",
                        event_name=event_name,
                        on_event=handler,
                        order=order,
                    )
                )

            def _on_spawn(evt):
                if self._active:
                    return
                count = self._spawn_all()
                self._active = count > 0
                dispatch_to_events2("maintenanceBotStatus", {"active": self._active, "count": count})

            def _on_despawn(evt):
                if not self._active:
                    return
                self._reset_all()
                dispatch_to_events2("maintenanceBotStatus", {"active": False, "count": 0})

            def _on_incident_added(evt):
                if not self._active:
                    return
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._handle_incident_added(payload)

            def _on_incident_removed(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                path = payload.get("incidentPath") or ""
                iid = self._path_to_incident_id(path)
                if iid and iid in self._incidents:
                    self._incidents[iid].status = "done"

            def _on_incidents_cleared(evt):
                for inc in self._incidents.values():
                    inc.status = "done"
                    inc.assigned_bot = None
                for bot in self._bots.values():
                    if bot.state in ("en_route", "resolving"):
                        bot.mover.stop()
                        bot.assigned_incident = None
                        bot.resolve_timer = 0.0
                        bot.state = "idle"
                self._incidents.clear()
                self._return_idle_bots()

            def _on_waypoints(evt):
                if not self._active:
                    return
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                route_id = str(payload.get("routeId") or "")
                if not route_id.startswith(ROUTE_ID_PREFIX):
                    return
                self._handle_waypoints(route_id, payload)

            _observe("maintenanceBotSpawn", _on_spawn)
            _observe("maintenanceBotDespawn", _on_despawn)
            _observe("incidentAdded", _on_incident_added, order=10)
            _observe("incidentRemoved", _on_incident_removed, order=10)
            _observe("incidentsCleared", _on_incidents_cleared, order=10)
            _observe("navmeshRouteWaypoints", _on_waypoints, order=20)

            print(f"{LOG_TAG} Extension started ({ext_id})")
        except Exception as e:
            print(f"{LOG_TAG} subscribe failed: {e}")

    # ------------------------------------------------------------------
    # Incident handling
    # ------------------------------------------------------------------

    def _handle_incident_added(self, payload: dict) -> None:
        path = str(payload.get("incidentPath") or "")
        pos_raw = payload.get("position") or {}
        severity = int(payload.get("severity", 1))
        iid = self._path_to_incident_id(path)
        if not iid or not path:
            return

        try:
            pos: Vec3 = (float(pos_raw.get("x", 0)), float(pos_raw.get("y", 0)), float(pos_raw.get("z", 0)))
        except Exception:
            return

        inc = IncidentRecord(
            incident_id=iid,
            incident_path=path,
            position=pos,
            severity=severity,
            status="reported",
        )
        self._incidents[iid] = inc
        print(f"{LOG_TAG} Incident queued: {iid} severity={severity}")

        self._send_update(incident=inc, action="reported")
        self._run_orchestrator()

    # ------------------------------------------------------------------
    # Travel time estimation (synchronous NavMesh queries)
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_travel_time(start_pos: Vec3, end_pos: Vec3) -> Optional[float]:
        """Compute NavMesh travel time (seconds) from *start_pos* to *end_pos*.

        Returns ``None`` when the path cannot be computed (e.g. NavMesh baking).
        """
        try:
            from younite.navmesh_route_extension.scripts.navmesh_shortest_path import (
                calculate_path_points,
                path_length_cm,
            )

            success, points_gf, _error = calculate_path_points(
                list(start_pos),
                list(end_pos),
                start_use_ground=False,
                camera_area_costs=None,
            )
            if not success or not points_gf:
                return None
            return path_length_cm(points_gf) / BOT_SPEED
        except Exception:
            return None

    @classmethod
    def _estimate_travel_time_or_fallback(cls, start_pos: Vec3, end_pos: Vec3) -> float:
        """NavMesh travel time with Euclidean XZ fallback."""
        t = cls._estimate_travel_time(start_pos, end_pos)
        if t is not None:
            return t
        return cls._dist_xz(start_pos, end_pos) / BOT_SPEED

    # ------------------------------------------------------------------
    # Orchestrator — assign bots to incidents
    # ------------------------------------------------------------------

    def _run_orchestrator(self) -> None:
        unassigned = [
            inc for inc in self._incidents.values()
            if inc.status == "reported" and inc.assigned_bot is None
        ]
        if not unassigned:
            return

        unassigned.sort(key=lambda i: i.severity, reverse=True)
        idle_bots = [b for b in self._bots.values() if b.state == "idle"]

        for inc in unassigned:
            if not idle_bots:
                break

            best_idle, best_idle_time = self._find_fastest_bot(idle_bots, inc.position)
            if best_idle is None:
                continue

            best_busy_time = self._estimate_best_busy_bot_time(inc.position)
            if best_busy_time is not None and best_busy_time < best_idle_time:
                print(
                    f"{LOG_TAG} Deferring {inc.incident_id}: "
                    f"busy bot ETA {best_busy_time:.1f}s vs idle {best_idle_time:.1f}s"
                )
                continue

            self._assign_bot(best_idle, inc, eta=best_idle_time)
            idle_bots.remove(best_idle)

    def _find_fastest_bot(
        self, candidates: List[BotRecord], target: Vec3
    ) -> Tuple[Optional[BotRecord], float]:
        """Return the idle bot with the shortest NavMesh travel time to *target*."""
        best: Optional[BotRecord] = None
        best_time = float("inf")
        stage = self._get_stage()

        for bot in candidates:
            bot_pos = self._get_prim_world_pos(stage, bot.prim_path) if stage else bot.spawn_pos
            if bot_pos is None:
                bot_pos = bot.spawn_pos
            t = self._estimate_travel_time_or_fallback(bot_pos, target)
            if t < best_time:
                best_time = t
                best = bot

        return best, best_time

    def _estimate_best_busy_bot_time(self, target_pos: Vec3) -> Optional[float]:
        """Estimate the fastest time any busy bot could reach *target_pos* after
        finishing its current task (resolve remaining + travel to new incident)."""
        best: Optional[float] = None

        for bot in self._bots.values():
            if bot.state not in ("en_route", "resolving"):
                continue
            inc = self._incidents.get(bot.assigned_incident or "")
            if not inc:
                continue

            if bot.state == "resolving":
                remaining = bot.resolve_timer
            else:
                stage = self._get_stage()
                bot_pos = self._get_prim_world_pos(stage, bot.prim_path) if stage else None
                if bot_pos:
                    remaining_travel = self._estimate_travel_time_or_fallback(bot_pos, inc.position)
                else:
                    remaining_travel = 0.0
                remaining = remaining_travel + RESOLVE_TIME_AVG

            travel_to_new = self._estimate_travel_time_or_fallback(inc.position, target_pos)
            total = remaining + travel_to_new

            if best is None or total < best:
                best = total

        return best

    def _pick_best_next_incident(
        self, candidates: List[IncidentRecord], from_pos: Vec3
    ) -> IncidentRecord:
        """Among *candidates*, pick the highest-severity incident; break ties by
        shortest NavMesh travel time from *from_pos*."""
        max_sev = max(c.severity for c in candidates)
        top = [c for c in candidates if c.severity == max_sev]
        if len(top) == 1:
            return top[0]
        best = top[0]
        best_time = float("inf")
        for c in top:
            t = self._estimate_travel_time_or_fallback(from_pos, c.position)
            if t < best_time:
                best_time = t
                best = c
        return best

    def _assign_bot(self, bot: BotRecord, inc: IncidentRecord, *, eta: float = 0.0) -> None:
        bot.state = "en_route"
        bot.assigned_incident = inc.incident_id
        bot.resolve_timer = 0.0
        bot.eta_seconds = eta
        inc.status = "resolving"
        inc.assigned_bot = bot.bot_id

        print(f"{LOG_TAG} Dispatching {bot.bot_id} -> {inc.incident_id} (severity {inc.severity}, ETA {eta:.1f}s)")
        self._send_update(bot=bot, incident=inc, action="dispatched")

        stage = self._get_stage()
        bot_pos = self._get_prim_world_pos(stage, bot.prim_path) if stage else bot.spawn_pos
        if bot_pos is None:
            bot_pos = bot.spawn_pos

        self._request_route(
            route_id=f"{ROUTE_ID_PREFIX}{bot.bot_id}",
            start_pos=bot_pos,
            end_pos=inc.position,
        )
        self._ensure_ticking()

    def _return_bot_to_spawn(self, bot: BotRecord) -> None:
        bot.state = "returning"
        bot.assigned_incident = None
        bot.resolve_timer = 0.0

        stage = self._get_stage()
        bot_pos = self._get_prim_world_pos(stage, bot.prim_path) if stage else bot.spawn_pos
        if bot_pos is None:
            bot_pos = bot.spawn_pos

        if self._dist_xz(bot_pos, bot.spawn_pos) < 50.0:
            bot.state = "idle"
            return

        self._request_route(
            route_id=f"{ROUTE_ID_PREFIX}{bot.bot_id}",
            start_pos=bot_pos,
            end_pos=bot.spawn_pos,
        )
        self._ensure_ticking()

    def _return_idle_bots(self) -> None:
        for bot in self._bots.values():
            if bot.state == "idle":
                stage = self._get_stage()
                pos = self._get_prim_world_pos(stage, bot.prim_path) if stage else bot.spawn_pos
                if pos and self._dist_xz(pos, bot.spawn_pos) > 50.0:
                    self._return_bot_to_spawn(bot)

    # ------------------------------------------------------------------
    # Waypoint reception
    # ------------------------------------------------------------------

    def _handle_waypoints(self, route_id: str, payload: dict) -> None:
        bot_id = route_id[len(ROUTE_ID_PREFIX):]
        bot = self._bots.get(bot_id)
        if not bot:
            return
        if bot.state not in ("en_route", "returning"):
            return
        # If the bot is already following waypoints, ignore recalculated routes
        # (e.g. after a NavMesh rebake). This prevents the bot from teleporting
        # back to the stale start position stored in the route extension.
        if bot.mover.is_active:
            return
        if not payload.get("success", False):
            print(f"{LOG_TAG} Route failed for {bot_id}")
            if bot.state == "en_route" and bot.assigned_incident:
                inc = self._incidents.get(bot.assigned_incident)
                if inc:
                    inc.status = "reported"
                    inc.assigned_bot = None
                bot.state = "idle"
                bot.assigned_incident = None
            return

        pts_raw = payload.get("points", [])
        waypoints: List[Vec3] = []
        for p in pts_raw:
            if isinstance(p, (list, tuple)) and len(p) >= 3:
                waypoints.append((float(p[0]), float(p[1]), float(p[2])))

        if len(waypoints) >= 2:
            bot.mover.set_waypoints(waypoints)
            dist_m = payload.get("distanceMetersBase")
            if dist_m is not None:
                bot.eta_seconds = (float(dist_m) * 100.0) / BOT_SPEED
            print(f"{LOG_TAG} {bot_id} received {len(waypoints)} waypoints (ETA {bot.eta_seconds:.1f}s)")
        else:
            print(f"{LOG_TAG} {bot_id}: too few waypoints ({len(waypoints)})")

    # ------------------------------------------------------------------
    # Per-frame tick
    # ------------------------------------------------------------------

    def _ensure_ticking(self) -> None:
        if self._ticking:
            return
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            ed = carb.eventdispatcher.get_eventdispatcher()
            self._update_sub = ed.observe_event(
                observer_name="younite.maintenance_bot_extension/tick",
                event_name=kit_app.GLOBAL_EVENT_UPDATE,
                on_event=self._tick,
                order=0,
            )
            self._ticking = True
        except Exception as e:
            print(f"{LOG_TAG} Failed to subscribe to update loop: {e}")

    def _tick(self, event) -> None:
        if not self._bots:
            return

        try:
            dt = float(getattr(event, "payload", {}).get("dt", 1.0 / 60.0))
        except Exception:
            dt = 1.0 / 60.0

        stage = self._get_stage()
        if not stage:
            return

        for bot in list(self._bots.values()):
            if bot.state == "en_route":
                self._tick_en_route(bot, dt, stage)
            elif bot.state == "resolving":
                self._tick_resolving(bot, dt)
            elif bot.state == "returning":
                self._tick_returning(bot, dt, stage)

        if self._rebake_pending:
            self._flush_rebake_if_safe()

    def _tick_en_route(self, bot: BotRecord, dt: float, stage) -> None:
        if not bot.mover.is_active:
            inc = self._incidents.get(bot.assigned_incident or "")
            if inc:
                resolve_time = random.uniform(RESOLVE_TIME_MIN, RESOLVE_TIME_MAX)
                bot.state = "resolving"
                bot.resolve_timer = resolve_time
                print(f"{LOG_TAG} {bot.bot_id} arrived at {inc.incident_id}, resolving in {resolve_time:.1f}s")
                self._send_update(bot=bot, incident=inc, action="arrived")
            else:
                bot.state = "idle"
                bot.assigned_incident = None
            return

        world_pos = self._get_prim_world_pos(stage, bot.prim_path)
        if world_pos is None:
            return
        result = bot.mover.update(dt, world_pos)
        if result:
            new_pos, new_rot = result
            self._apply_transform(stage, bot.prim_path, new_pos, new_rot)
            if not bot.mover.is_active:
                inc = self._incidents.get(bot.assigned_incident or "")
                if inc:
                    resolve_time = random.uniform(RESOLVE_TIME_MIN, RESOLVE_TIME_MAX)
                    bot.state = "resolving"
                    bot.resolve_timer = resolve_time
                    print(f"{LOG_TAG} {bot.bot_id} arrived at {inc.incident_id}, resolving in {resolve_time:.1f}s")
                    self._send_update(bot=bot, incident=inc, action="arrived")

    def _tick_resolving(self, bot: BotRecord, dt: float) -> None:
        bot.resolve_timer -= dt
        if bot.resolve_timer > 0:
            return

        inc = self._incidents.get(bot.assigned_incident or "")
        if inc:
            inc.status = "done"
            inc.assigned_bot = None
            print(f"{LOG_TAG} {bot.bot_id} resolved {inc.incident_id}")
            self._send_update(bot=bot, incident=inc, action="resolved")

            if self._dispatch:
                self._dispatch("incidentRemove", {
                    "incidentPath": inc.incident_path,
                    "skipRebake": True,
                })
                self._rebake_pending = True

        resolved_pos = inc.position if inc else bot.spawn_pos
        bot.assigned_incident = None
        bot.resolve_timer = 0.0
        bot.eta_seconds = 0.0

        pending = [
            i for i in self._incidents.values()
            if i.status == "reported" and i.assigned_bot is None
        ]
        if pending:
            best_next = self._pick_best_next_incident(pending, resolved_pos)
            eta = self._estimate_travel_time_or_fallback(resolved_pos, best_next.position)
            self._assign_bot(bot, best_next, eta=eta)
        else:
            self._return_bot_to_spawn(bot)
            self._flush_rebake_if_safe()

    def _tick_returning(self, bot: BotRecord, dt: float, stage) -> None:
        if not bot.mover.is_active:
            bot.state = "idle"
            print(f"{LOG_TAG} {bot.bot_id} returned to spawn")
            self._run_orchestrator()
            return

        world_pos = self._get_prim_world_pos(stage, bot.prim_path)
        if world_pos is None:
            return
        result = bot.mover.update(dt, world_pos)
        if result:
            new_pos, new_rot = result
            self._apply_transform(stage, bot.prim_path, new_pos, new_rot)
            if not bot.mover.is_active:
                bot.state = "idle"
                print(f"{LOG_TAG} {bot.bot_id} returned to spawn")
                self._run_orchestrator()

    # ------------------------------------------------------------------
    # Deferred rebake
    # ------------------------------------------------------------------

    def _flush_rebake_if_safe(self) -> None:
        """Trigger a single NavMesh rebake if no bots are still resolving."""
        if not self._rebake_pending:
            return
        any_resolving = any(b.state == "resolving" for b in self._bots.values())
        if any_resolving:
            return
        self._rebake_pending = False
        if self._dispatch:
            self._dispatch("navmeshRebakeRequest", {})
            print(f"{LOG_TAG} Deferred NavMesh rebake triggered")

    # ------------------------------------------------------------------
    # Spawning / despawning
    # ------------------------------------------------------------------

    def _spawn_all(self) -> int:
        try:
            import omni.usd
            from pxr import Gf, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                print(f"{LOG_TAG} No stage available")
                return 0

            model_path = self._resolve_model_path(stage)
            spawn_points = self._collect_spawn_points(stage)

            if not spawn_points:
                print(f"{LOG_TAG} No spawn points found with prefix {SPAWN_POINT_PREFIX}")
                return 0

            count = 0
            for idx, (sp_path, world_pos) in enumerate(spawn_points, start=1):
                bot_id = f"bot_{idx:02d}"
                bot_path = f"{BOT_PRIM_PREFIX}{idx:02d}"

                existing = stage.GetPrimAtPath(bot_path)
                if existing and existing.IsValid():
                    stage.RemovePrim(bot_path)

                prim = stage.DefinePrim(bot_path, "Xform")
                if model_path:
                    prim.GetReferences().AddReference(model_path)
                else:
                    self._create_fallback_capsule(stage, bot_path)

                xf = UsdGeom.Xformable(prim)
                xf.ClearXformOpOrder()
                xf.AddTranslateOp().Set(Gf.Vec3d(
                    float(world_pos[0]),
                    float(world_pos[1]) + 80.0,
                    float(world_pos[2]),
                ))
                xf.AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 0))
                xf.AddScaleOp().Set(Gf.Vec3f(1, 1, 1))

                self._bots[bot_id] = BotRecord(
                    bot_id=bot_id,
                    prim_path=bot_path,
                    spawn_pos=(float(world_pos[0]), float(world_pos[1]) + 80.0, float(world_pos[2])),
                )
                count += 1

            print(f"{LOG_TAG} Spawned {count} maintenance bot(s)")
            return count
        except Exception as e:
            print(f"{LOG_TAG} spawn error: {e}")
            return 0

    def _reset_all(self) -> None:
        try:
            import omni.usd
            stage = omni.usd.get_context().get_stage()
            if stage:
                for bot in self._bots.values():
                    bot.mover.stop()
                    prim = stage.GetPrimAtPath(bot.prim_path)
                    if prim and prim.IsValid():
                        stage.RemovePrim(bot.prim_path)
        except Exception as e:
            print(f"{LOG_TAG} despawn error: {e}")

        self._bots.clear()
        self._incidents.clear()
        self._active = False
        print(f"{LOG_TAG} All maintenance bots removed and state reset")

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------

    def _send_update(
        self,
        *,
        bot: Optional[BotRecord] = None,
        incident: Optional[IncidentRecord] = None,
        action: str = "",
    ) -> None:
        if not self._dispatch:
            return
        payload: dict = {"action": action}
        if bot:
            payload["botId"] = bot.bot_id
            if bot.eta_seconds > 0:
                payload["eta"] = round(bot.eta_seconds, 1)
        if incident:
            payload["incidentId"] = incident.incident_id
            payload["severity"] = incident.severity
            payload["status"] = incident.status
            payload["position"] = {
                "x": incident.position[0],
                "y": incident.position[1],
                "z": incident.position[2],
            }
        self._dispatch("maintenanceBotIncidentUpdate", payload)

    # ------------------------------------------------------------------
    # NavMesh route request
    # ------------------------------------------------------------------

    @staticmethod
    def _request_route(route_id: str, start_pos: Vec3, end_pos: Vec3) -> None:
        from younite.messaging_core_extension.message_utils import dispatch_to_events2
        payload = {
            "routeId": route_id,
            "startPos": [start_pos[0], start_pos[1], start_pos[2]],
            "endPos": [end_pos[0], end_pos[1], end_pos[2]],
            "drawPath": False,
            "enablePeriodicRecalc": False,
        }
        try:
            dispatch_to_events2("navmeshRouteCalculate", payload)
        except Exception as e:
            print(f"{LOG_TAG} Failed to request route: {e}")

    # ------------------------------------------------------------------
    # USD helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_stage():
        try:
            import omni.usd
            ctx = omni.usd.get_context()
            return ctx.get_stage() if ctx else None
        except Exception:
            return None

    @staticmethod
    def _get_prim_world_pos(stage, prim_path: str) -> Optional[Vec3]:
        from pxr import Usd, UsdGeom
        prim = stage.GetPrimAtPath(prim_path)
        if not (prim and prim.IsValid()):
            return None
        xf = UsdGeom.Xformable(prim)
        mat = xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        t = mat.ExtractTranslation()
        return (float(t[0]), float(t[1]), float(t[2]))

    @staticmethod
    def _apply_transform(stage, prim_path: str, translate: Vec3, rotate_xyz: Vec3) -> None:
        from pxr import Gf, UsdGeom
        prim = stage.GetPrimAtPath(prim_path)
        if not (prim and prim.IsValid()):
            return
        xf = UsdGeom.Xformable(prim)
        tr_op = None
        for op in xf.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate and "pivot" not in op.GetName():
                tr_op = op
                break
        if not tr_op:
            tr_op = xf.AddTranslateOp()
        tr_op.Set(Gf.Vec3d(float(translate[0]), float(translate[1]), float(translate[2])))

        rot_op = None
        for op in xf.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
                rot_op = op
                break
        if not rot_op:
            rot_op = xf.AddRotateXYZOp()
        rot_op.Set(Gf.Vec3f(float(rotate_xyz[0]), float(rotate_xyz[1]), float(rotate_xyz[2])))

    @staticmethod
    def _collect_spawn_points(stage) -> list:
        from pxr import Usd, UsdGeom
        results = []
        idx = 1
        while True:
            sp_path = f"{SPAWN_POINT_PREFIX}{idx:02d}"
            prim = stage.GetPrimAtPath(sp_path)
            if not (prim and prim.IsValid()):
                break
            xf = UsdGeom.Xformable(prim)
            mat = xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            t = mat.ExtractTranslation()
            results.append((sp_path, (float(t[0]), float(t[1]), float(t[2]))))
            idx += 1
        return results

    @staticmethod
    def _resolve_model_path(stage) -> Optional[str]:
        try:
            root_layer = stage.GetRootLayer()
            scene_dir = os.path.dirname(root_layer.realPath)
            candidate = os.path.normpath(os.path.join(scene_dir, MODEL_RELATIVE_PATH))
            if os.path.isfile(candidate):
                return candidate
            data_dir = os.path.normpath(os.path.join(scene_dir, "..", MODEL_RELATIVE_PATH))
            if os.path.isfile(data_dir):
                return data_dir
        except Exception:
            pass
        return None

    @staticmethod
    def _create_fallback_capsule(stage, prim_path: str) -> None:
        from pxr import Gf, UsdGeom, Vt
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            prim = stage.DefinePrim(prim_path, "Capsule")
        capsule = UsdGeom.Capsule(prim)
        capsule.CreateHeightAttr().Set(120.0)
        capsule.CreateRadiusAttr().Set(30.0)
        capsule.CreateAxisAttr().Set("Y")
        capsule.CreateDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0.2, 0.6, 1.0)]))

    @staticmethod
    def _dist_xz(a: Vec3, b: Vec3) -> float:
        dx = a[0] - b[0]
        dz = a[2] - b[2]
        return math.sqrt(dx * dx + dz * dz)

    @staticmethod
    def _path_to_incident_id(path: str) -> Optional[str]:
        if not path:
            return None
        parts = path.rstrip("/").split("/")
        return parts[-1] if parts else None

    # ------------------------------------------------------------------

    def on_shutdown(self):
        if self._active:
            try:
                self._reset_all()
            except Exception:
                pass
        self._update_sub = None
        self._ticking = False
        self._subs.clear()
        self._active = False
