"""
Hybrid tile manager: distance-based culling in first person, show-all in bird's eye.

Discovers city tile prims at runtime, computes their bounding-box centres,
then runs a 1 Hz async loop that moves each tile between three zones:

  Active  — loaded + visible
  Warmup  — loaded + invisible (preloaded for fast activation)
  Outer   — invisible + payload unloaded (frees GPU memory)

Culling strategy is chosen automatically via the /younite/camera/viewType
carb setting written by player_core:

  firstPerson → distance from player XZ position; full payload load/unload
  birdEye     → all tiles shown, no culling

Bird's-eye shows everything to avoid lag spikes from USD composition
re-evaluation and BVH rebuilds during rapid camera panning.  When the user
switches back to first-person, distance-based culling resumes and gradually
unloads distant tiles through the normal cooldown path.

All mutations go through the Payload Orchestrator for frame-budgeted execution.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

# ── Distance-mode constants ───────────────────────────────────────────
VISIBLE_RADIUS = 50000.0
WARMUP_RADIUS = 100000.0
HYSTERESIS_FACTOR = 1.15
UPDATE_INTERVAL = 1.0
MAX_OPS_PER_TICK = 5

# ── Frustum-mode constants (bird's eye) ───────────────────────────────
FRUSTUM_ACTIVE_MARGIN = 3.5   # 1.0 = screen edge
FRUSTUM_WARMUP_MARGIN = 7.0
FRUSTUM_HYSTERESIS = 1.15
UNLOAD_COOLDOWN = 10.0

TILE_PARENTS = [
    "/World/CU_DT_8km2_Project_Scene/Geometry",
]
EDITED_TILE_PREFIX = "/World/edited_tile_"
NEVER_MANAGE = {
    "/World/Skandinavium",
    "/World/Skandinavium_lights",
}


class TileZone(Enum):
    ACTIVE = "active"
    WARMUP = "warmup"
    OUTER = "outer"


@dataclass
class TrackedTile:
    path: str
    cx: float
    cy: float
    cz: float
    has_payload: bool
    zone: TileZone = TileZone.ACTIVE
    active_enter_sq: float = 0.0
    active_leave_sq: float = 0.0
    warmup_enter_sq: float = 0.0
    warmup_leave_sq: float = 0.0
    outer_since: float = 0.0


class TileManager:

    def __init__(self, player_location_service):
        self._pls = player_location_service
        self._tiles: List[TrackedTile] = []
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_mode_tag: Optional[str] = None
        self._birdeye = False

    # ── Discovery ─────────────────────────────────────────────────────

    def discover(self) -> int:
        import omni.usd
        from pxr import Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return 0

        bbox_cache = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]
        )
        self._tiles.clear()

        for parent_path in TILE_PARENTS:
            parent = stage.GetPrimAtPath(parent_path)
            if not parent or not parent.IsValid():
                continue
            for child in parent.GetChildren():
                self._try_register(child, bbox_cache)

        world = stage.GetPrimAtPath("/World")
        if world and world.IsValid():
            for child in world.GetChildren():
                if str(child.GetPath()).startswith(EDITED_TILE_PREFIX):
                    self._try_register(child, bbox_cache)

        return len(self._tiles)

    def _try_register(self, prim, bbox_cache) -> None:
        path_str = str(prim.GetPath())
        if path_str in NEVER_MANAGE:
            return

        try:
            bbox = bbox_cache.ComputeWorldBound(prim)
            rng = bbox.ComputeAlignedRange()
            if rng.IsEmpty():
                return
            centre = (rng.GetMin() + rng.GetMax()) / 2.0
            cx, cy, cz = float(centre[0]), float(centre[1]), float(centre[2])
        except Exception:
            return

        vis_sq = VISIBLE_RADIUS ** 2
        warm_sq = WARMUP_RADIUS ** 2

        self._tiles.append(TrackedTile(
            path=path_str, cx=cx, cy=cy, cz=cz,
            has_payload=prim.HasPayload(),
            active_enter_sq=vis_sq,
            active_leave_sq=(VISIBLE_RADIUS * HYSTERESIS_FACTOR) ** 2,
            warmup_enter_sq=warm_sq,
            warmup_leave_sq=(WARMUP_RADIUS * HYSTERESIS_FACTOR) ** 2,
        ))

    # ── Async loop ────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._run())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._restore_all()

    async def _run(self) -> None:
        try:
            while self._running:
                self._update_zones()
                self._process_deferred_unloads()
                await asyncio.sleep(UPDATE_INTERVAL)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    # ── View-mode detection & frustum helpers ─────────────────────────

    @staticmethod
    def _is_birdeye() -> bool:
        try:
            import carb.settings
            return str(carb.settings.get_settings().get(
                "/younite/camera/viewType")) == "birdEye"
        except Exception:
            return False

    @staticmethod
    def _get_vp_matrix():
        """Combined view-projection matrix with viewport aspect-ratio correction."""
        try:
            import omni.usd
            import omni.kit.viewport.utility as vp_utils
            from pxr import UsdGeom, Usd

            vp = vp_utils.get_active_viewport()
            if not vp:
                return None

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return None

            cam_prim = stage.GetPrimAtPath(vp.camera_path)
            if not cam_prim or not cam_prim.IsValid():
                return None

            gf_cam = UsdGeom.Camera(cam_prim).GetCamera(Usd.TimeCode.Default())

            res = vp.resolution
            if res and res[0] > 0 and res[1] > 0:
                gf_cam.verticalAperture = (
                    gf_cam.horizontalAperture / (res[0] / res[1]))

            f = gf_cam.frustum
            return f.ComputeViewMatrix() * f.ComputeProjectionMatrix()
        except Exception:
            return None

    @staticmethod
    def _ndc_extent(tile: TrackedTile, vp_mat) -> float:
        """max(|ndc_x|, |ndc_y|) for a tile centre; inf if behind camera."""
        x, y, z = tile.cx, tile.cy, tile.cz
        c0 = vp_mat.GetColumn(0)
        c1 = vp_mat.GetColumn(1)
        c3 = vp_mat.GetColumn(3)

        clip_x = x * c0[0] + y * c0[1] + z * c0[2] + c0[3]
        clip_y = x * c1[0] + y * c1[1] + z * c1[2] + c1[3]
        clip_w = x * c3[0] + y * c3[1] + z * c3[2] + c3[3]

        if clip_w <= 0:
            return float("inf")
        return max(abs(clip_x / clip_w), abs(clip_y / clip_w))

    @staticmethod
    def _desired_zone_frustum(tile: TrackedTile, ndc_ext: float) -> TileZone:
        a_in = FRUSTUM_ACTIVE_MARGIN
        a_out = FRUSTUM_ACTIVE_MARGIN * FRUSTUM_HYSTERESIS
        w_in = FRUSTUM_WARMUP_MARGIN
        w_out = FRUSTUM_WARMUP_MARGIN * FRUSTUM_HYSTERESIS

        if tile.zone == TileZone.ACTIVE:
            if ndc_ext > w_out:
                return TileZone.OUTER
            if ndc_ext > a_out:
                return TileZone.WARMUP
            return TileZone.ACTIVE

        if tile.zone == TileZone.WARMUP:
            if ndc_ext <= a_in:
                return TileZone.ACTIVE
            if ndc_ext > w_out:
                return TileZone.OUTER
            return TileZone.WARMUP

        if ndc_ext <= a_in:
            return TileZone.ACTIVE
        if ndc_ext <= w_in:
            return TileZone.WARMUP
        return TileZone.OUTER

    # ── Core update ───────────────────────────────────────────────────

    def _update_zones(self) -> None:
        if not self._tiles:
            return

        pos = self._pls.get_player_world_position() if self._pls else None
        if pos is None:
            return

        is_birdeye = self._is_birdeye()
        self._birdeye = is_birdeye

        mode_tag = "B" if is_birdeye else "D"
        if self._last_mode_tag != mode_tag:
            self._last_mode_tag = mode_tag
            if is_birdeye:
                self._show_all()

        if is_birdeye:
            return

        px, pz = float(pos[0]), float(pos[2])
        ops = 0
        for tile in self._tiles:
            if ops >= MAX_OPS_PER_TICK:
                break

            dx, dz = tile.cx - px, tile.cz - pz
            desired = self._desired_zone_distance(
                tile, dx * dx + dz * dz)

            if desired != tile.zone:
                self._transition(tile, desired)
                ops += 1

    @staticmethod
    def _desired_zone_distance(tile: TrackedTile, dist_sq: float) -> TileZone:
        if tile.zone == TileZone.ACTIVE:
            if dist_sq > tile.warmup_leave_sq:
                return TileZone.OUTER
            if dist_sq > tile.active_leave_sq:
                return TileZone.WARMUP
            return TileZone.ACTIVE

        if tile.zone == TileZone.WARMUP:
            if dist_sq <= tile.active_enter_sq:
                return TileZone.ACTIVE
            if dist_sq > tile.warmup_leave_sq:
                return TileZone.OUTER
            return TileZone.WARMUP

        if dist_sq <= tile.active_enter_sq:
            return TileZone.ACTIVE
        if dist_sq <= tile.warmup_enter_sq:
            return TileZone.WARMUP
        return TileZone.OUTER

    def _transition(self, tile: TrackedTile, target: TileZone) -> None:
        from younite.payload_orchestrator_core_extension import (
            show, hide, load_prim, Priority,
        )

        prev = tile.zone
        tile.zone = target

        if target == TileZone.ACTIVE:
            tile.outer_since = 0.0
            if tile.has_payload and prev == TileZone.OUTER:
                load_prim(tile.path, Priority.HIGH, source="tile_mgr")
            show(tile.path, Priority.HIGH, source="tile_mgr")

        elif target == TileZone.WARMUP:
            tile.outer_since = 0.0
            if tile.has_payload and prev == TileZone.OUTER:
                load_prim(tile.path, Priority.BACKGROUND, source="tile_mgr")
            hide(tile.path, Priority.MEDIUM, source="tile_mgr")

        elif target == TileZone.OUTER:
            hide(tile.path, Priority.LOW, source="tile_mgr")
            tile.outer_since = time.monotonic()

    # ── Bird's-eye show-all ─────────────────────────────────────────

    def _show_all(self) -> None:
        """Restore every non-active tile to ACTIVE (load if needed, show)."""
        from younite.payload_orchestrator_core_extension import (
            show, load_prim, Priority,
        )

        restored = 0
        for tile in self._tiles:
            if tile.zone == TileZone.ACTIVE:
                continue
            if tile.has_payload and tile.zone == TileZone.OUTER and tile.outer_since == 0.0:
                load_prim(tile.path, Priority.HIGH, source="tile_mgr")
            show(tile.path, Priority.HIGH, source="tile_mgr")
            tile.zone = TileZone.ACTIVE
            tile.outer_since = 0.0
            restored += 1

    # ── Deferred unloads ─────────────────────────────────────────────

    def _process_deferred_unloads(self) -> None:
        if self._birdeye:
            return

        from younite.payload_orchestrator_core_extension import (
            unload_prim, Priority,
        )

        now = time.monotonic()
        for tile in self._tiles:
            if (tile.zone == TileZone.OUTER
                    and tile.has_payload
                    and tile.outer_since > 0
                    and now - tile.outer_since >= UNLOAD_COOLDOWN):
                unload_prim(tile.path, Priority.LOW, source="tile_mgr")
                tile.outer_since = 0.0

    # ── Shutdown restore ──────────────────────────────────────────────

    def _restore_all(self) -> None:
        from younite.payload_orchestrator_core_extension import (
            show, load_prim, Priority,
        )

        restored = 0
        for tile in self._tiles:
            if tile.zone != TileZone.ACTIVE:
                if tile.has_payload and tile.zone == TileZone.OUTER and tile.outer_since == 0.0:
                    load_prim(tile.path, Priority.CRITICAL, source="tile_mgr")
                show(tile.path, Priority.CRITICAL, source="tile_mgr")
                tile.zone = TileZone.ACTIVE
                tile.outer_since = 0.0
                restored += 1

