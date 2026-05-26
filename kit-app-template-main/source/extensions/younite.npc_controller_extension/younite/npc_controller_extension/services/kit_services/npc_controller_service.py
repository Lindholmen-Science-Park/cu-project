"""
NPC Controller Service

Manages multiple NPC characters that follow NavMesh-computed routes.

Usage flow:
  1. ``npcSpawn`` event  → registers an NPC prim + assigns a routeId
  2. ``navmeshRouteCalculate`` is dispatched (by caller or automatically)
  3. ``navmeshRouteWaypoints`` arrives → fed into the NPC's mover
  4. Per-frame ``_tick`` drives every active NPC along its waypoints

Events consumed:
  - ``npcSpawn``    — register / update an NPC    { npcId, primPath, routeId, speed?, loop?, start, end }
  - ``npcStop``     — stop one or all NPCs        { npcId? | all }
  - ``navmeshRouteWaypoints`` — waypoints from the navmesh extension

Events emitted:
  - ``npcArrived``  — NPC reached end of route    { npcId, routeId }
  - ``npcStatus``   — state changes               { npcId, active }
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import omni.kit.app as kit_app
import omni.usd
import os
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

from ...scripts.npc_mover import NpcMover
from younite.messaging_core_extension.message_utils import dispatch_to_events2

LOG_TAG = "[npc_controller]"


@dataclass
class _NpcRecord:
    npc_id: str
    prim_path: str
    route_id: str
    mover: NpcMover
    speed: float = 150.0
    loop: bool = False


class NpcControllerService:
    """Manages NPC lifecycle, waypoint consumption, and per-frame updates."""

    def __init__(self):
        self._npcs: Dict[str, _NpcRecord] = {}
        self._update_sub = None
        self._ticking = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def spawn_npc(
        self,
        npc_id: str,
        prim_path: str,
        route_id: str,
        *,
        speed: float = 150.0,
        loop: bool = False,
        start_ref: Any = None,
        end_ref: Any = None,
        draw_path: bool = False,
        model: Optional[str] = None,
    ) -> bool:
        """
        Register an NPC to be driven along a navmesh route.

        If *start_ref* and *end_ref* are provided the service will also fire
        a ``navmeshRouteCalculate`` event so the route extension computes the
        waypoints automatically.
        """
        try:
            npc_id = str(npc_id or "npc_default")
            prim_path = str(prim_path)
            route_id = str(route_id or npc_id)

            stage = self._get_stage()
            if stage:
                prim = stage.GetPrimAtPath(prim_path)
                if not (prim and prim.IsValid()):
                    if start_ref is not None:
                        self._ensure_test_prim(stage, prim_path, start_ref, model=model)
                    else:
                        print(f"{LOG_TAG} Prim not found: {prim_path}")
                        return False

            mover = NpcMover(
                npc_id=npc_id,
                prim_path=prim_path,
                speed=float(speed),
                loop=bool(loop),
            )

            rec = _NpcRecord(
                npc_id=npc_id,
                prim_path=prim_path,
                route_id=route_id,
                mover=mover,
                speed=float(speed),
                loop=bool(loop),
            )
            self._npcs[npc_id] = rec

            self._ensure_ticking()

            dispatch_to_events2("npcStatus", {"npcId": npc_id, "active": True})
            print(f"{LOG_TAG} Spawned NPC '{npc_id}' on prim {prim_path}, routeId={route_id}")

            # Kick off route calculation if endpoints provided
            if start_ref is not None and end_ref is not None:
                self._request_route(route_id, start_ref, end_ref, draw_path=draw_path)

            return True
        except Exception as e:
            print(f"{LOG_TAG} spawn_npc error: {e}")
            return False

    def stop_npc(self, npc_id: str) -> None:
        rec = self._npcs.pop(str(npc_id), None)
        if not rec:
            return
        rec.mover.stop()
        dispatch_to_events2("npcStatus", {"npcId": rec.npc_id, "active": False})
        # Also stop the navmesh route so the visualization cleans up
        try:
            dispatch_to_events2("navmeshRouteStop", {"routeId": rec.route_id})
        except Exception:
            pass
        # Remove the test prim from the stage
        self._remove_prim(rec.prim_path)
        print(f"{LOG_TAG} Stopped NPC '{npc_id}'")

    def stop_all(self) -> None:
        for npc_id in list(self._npcs.keys()):
            self.stop_npc(npc_id)

    # ------------------------------------------------------------------
    # Waypoint consumption (called by extension when navmeshRouteWaypoints arrives)
    # ------------------------------------------------------------------

    def on_route_waypoints(self, payload: Dict[str, Any]) -> None:
        route_id = str(payload.get("routeId") or "")
        if not bool(payload.get("success", False)):
            return

        pts_raw = payload.get("points")
        if not isinstance(pts_raw, list) or len(pts_raw) < 2:
            return

        waypoints: List[Tuple[float, float, float]] = []
        for p in pts_raw:
            if isinstance(p, (list, tuple)) and len(p) >= 3:
                waypoints.append((float(p[0]), float(p[1]), float(p[2])))
        if len(waypoints) < 2:
            return

        fed = 0
        for rec in self._npcs.values():
            if rec.route_id == route_id:
                rec.mover.set_waypoints(waypoints)
                fed += 1

        if fed:
            print(f"{LOG_TAG} Fed {len(waypoints)} waypoints (routeId={route_id}) to {fed} NPC(s)")

    # ------------------------------------------------------------------
    # Per-frame tick
    # ------------------------------------------------------------------

    def _ensure_ticking(self) -> None:
        if self._ticking:
            return
        try:
            import carb.eventdispatcher
            ed = carb.eventdispatcher.get_eventdispatcher()
            self._update_sub = ed.observe_event(
                observer_name="younite.npc_controller_extension/tick",
                event_name=kit_app.GLOBAL_EVENT_UPDATE,
                on_event=self._tick,
                order=0,
            )
            self._ticking = True
        except Exception as e:
            print(f"{LOG_TAG} Failed to subscribe to update loop: {e}")

    def _tick(self, event) -> None:
        if not self._npcs:
            return

        try:
            dt = float(getattr(event, "payload", {}).get("dt", 1.0 / 60.0))
        except Exception:
            dt = 1.0 / 60.0

        stage = self._get_stage()
        if not stage:
            return

        arrived: List[str] = []
        for rec in list(self._npcs.values()):
            if not rec.mover.is_active:
                continue
            try:
                world_pos = self._get_prim_world_pos(stage, rec.prim_path)
                if world_pos is None:
                    continue

                result = rec.mover.update(dt, world_pos)
                if result is None:
                    if not rec.mover.is_active:
                        arrived.append(rec.npc_id)
                    continue

                new_pos, new_rot = result
                self._apply_transform(stage, rec.prim_path, new_pos, new_rot)

                if not rec.mover.is_active:
                    arrived.append(rec.npc_id)
            except Exception as e:
                print(f"{LOG_TAG} tick error for '{rec.npc_id}': {e}")

        for npc_id in arrived:
            rec = self._npcs.get(npc_id)
            if rec:
                dispatch_to_events2("npcArrived", {
                    "npcId": rec.npc_id,
                    "routeId": rec.route_id,
                })
                print(f"{LOG_TAG} NPC '{npc_id}' arrived at destination")

    # ------------------------------------------------------------------
    # USD helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_stage():
        try:
            ctx = omni.usd.get_context()
            return ctx.get_stage() if ctx else None
        except Exception:
            return None

    def _remove_prim(self, prim_path: str) -> None:
        """Remove a prim created by _ensure_test_prim."""
        try:
            stage = self._get_stage()
            if not stage:
                return
            prim = stage.GetPrimAtPath(prim_path)
            if prim and prim.IsValid():
                stage.RemovePrim(prim_path)
                print(f"{LOG_TAG} Removed prim {prim_path}")
        except Exception as e:
            print(f"{LOG_TAG} Failed to remove prim {prim_path}: {e}")

    @staticmethod
    def _get_prim_world_pos(stage, prim_path: str) -> Optional[Tuple[float, float, float]]:
        prim = stage.GetPrimAtPath(prim_path)
        if not (prim and prim.IsValid()):
            return None
        xf = UsdGeom.Xformable(prim)
        mat = xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        t = mat.ExtractTranslation()
        return (float(t[0]), float(t[1]), float(t[2]))

    @staticmethod
    def _apply_transform(
        stage,
        prim_path: str,
        translate: Tuple[float, float, float],
        rotate_xyz: Tuple[float, float, float],
    ) -> None:
        prim = stage.GetPrimAtPath(prim_path)
        if not (prim and prim.IsValid()):
            return

        xf = UsdGeom.Xformable(prim)

        # Translate
        tr_op = None
        for op in xf.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate and "pivot" not in op.GetName():
                tr_op = op
                break
        if not tr_op:
            tr_op = xf.AddTranslateOp()
        tr_op.Set(Gf.Vec3d(float(translate[0]), float(translate[1]), float(translate[2])))

        # Rotation
        rot_op = None
        for op in xf.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
                rot_op = op
                break
        if not rot_op:
            rot_op = xf.AddRotateXYZOp()
        rot_op.Set(Gf.Vec3f(float(rotate_xyz[0]), float(rotate_xyz[1]), float(rotate_xyz[2])))

    @staticmethod
    def _ensure_test_prim(stage, prim_path: str, start_ref: Any, *, model: Optional[str] = None) -> None:
        """Create an NPC prim at the start position.

        If *model* is provided (relative asset path like ``Assets/NPC/npc_capsule.usda``),
        the prim is created as an Xform that references the asset file.  Otherwise a
        procedural orange Capsule is created as a fallback.
        """
        try:
            from younite.navmesh_route_extension.scripts.navmesh_shortest_path import resolve_position
            start_pos = resolve_position(stage, start_ref, use_ground=False)
        except Exception:
            if isinstance(start_ref, (list, tuple)) and len(start_ref) >= 3:
                start_pos = Gf.Vec3d(float(start_ref[0]), float(start_ref[1]), float(start_ref[2]))
            else:
                print(f"{LOG_TAG} Cannot resolve start position for test prim")
                return

        if model:
            asset_path = NpcControllerService._resolve_model_path(stage, model)
            prim = stage.DefinePrim(prim_path, "Xform")
            prim.GetReferences().AddReference(asset_path)
            print(f"{LOG_TAG} Created NPC prim at {prim_path} (model: {asset_path})")
        else:
            prim = stage.DefinePrim(prim_path, "Capsule")
            capsule = UsdGeom.Capsule(prim)
            capsule.CreateHeightAttr().Set(100.0)
            capsule.CreateRadiusAttr().Set(25.0)
            capsule.CreateAxisAttr().Set("Y")
            capsule.CreateDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(1.0, 0.5, 0.0)]))
            print(f"{LOG_TAG} Created fallback capsule prim at {prim_path}")

        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(
            float(start_pos[0]),
            float(start_pos[1]) + 80.0,
            float(start_pos[2]),
        ))
        xf.AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 0))
        xf.AddScaleOp().Set(Gf.Vec3f(1, 1, 1))

    @staticmethod
    def _resolve_model_path(stage, relative_path: str) -> str:
        """Resolve a model path relative to the scene's data directory."""
        try:
            root_layer = stage.GetRootLayer()
            scene_dir = os.path.dirname(root_layer.realPath)
            # Assets are under the data root, scenes are in data/scenes/
            data_dir = os.path.dirname(scene_dir) if scene_dir.endswith("scenes") else scene_dir
            abs_path = os.path.normpath(os.path.join(data_dir, relative_path))
            if os.path.isfile(abs_path):
                return abs_path
        except Exception:
            pass
        return relative_path

    # ------------------------------------------------------------------
    # Route request helper
    # ------------------------------------------------------------------

    @staticmethod
    def _request_route(
        route_id: str,
        start_ref: Any,
        end_ref: Any,
        *,
        draw_path: bool = False,
    ) -> None:
        """Fire a navmeshRouteCalculate event so the route extension computes waypoints."""
        payload: Dict[str, Any] = {"routeId": route_id, "drawPath": draw_path}
        if isinstance(start_ref, str):
            payload["startpointPath"] = start_ref
        elif isinstance(start_ref, (list, tuple)) and len(start_ref) >= 3:
            payload["startPos"] = [float(start_ref[0]), float(start_ref[1]), float(start_ref[2])]
        if isinstance(end_ref, str):
            payload["endpointPath"] = end_ref
        elif isinstance(end_ref, (list, tuple)) and len(end_ref) >= 3:
            payload["endPos"] = [float(end_ref[0]), float(end_ref[1]), float(end_ref[2])]
        try:
            dispatch_to_events2("navmeshRouteCalculate", payload)
        except Exception as e:
            print(f"{LOG_TAG} Failed to request route: {e}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        self.stop_all()
        self._update_sub = None
        self._ticking = False
