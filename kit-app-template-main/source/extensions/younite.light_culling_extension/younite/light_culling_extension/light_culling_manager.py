"""
Per-group distance-based light culling.

Toggles UsdLux light visibility on the session layer based on XZ distance
from the player.  Each light is assigned a cull distance derived from its
name prefix (arena bowl lights get a large radius, corridor lights a small
one).  A per-light ``app:cull:distance`` USD attribute overrides the group
default when present.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ── Group → cull-distance mapping (USD units, 1 unit = 1 cm) ────────
# Checked in order — first prefix match wins.
GROUP_DISTANCES: List[Tuple[str, float]] = [
    # Arena bowl — visible across the whole arena (~200 m)
    ("L_Arena_Ceiling",          20000.0),
    ("L_Arena_Facade",           20000.0),
    ("L_Glod_",                  20000.0),
    # Foyer — large open area (~100 m)
    ("L_Foyer_",                 10000.0),
    # VIP / extension areas (~80 m)
    ("L_VIP_Extension_",          8000.0),
    ("L_Extension_",              8000.0),
    # Exterior (~100 m)
    ("L_Facade_Uplights",        10000.0),
    ("L_Context_Streetlight",    10000.0),
    ("L_Exterior_",              10000.0),
    # Corridors & rooms — only visible up close (~50 m)
    ("Arealight_Corridor",        5000.0),
    ("Arealight_Room",            5000.0),
    ("Arealight_Bigroom",         5000.0),
    ("Arealight_Rooms",           5000.0),
]
DEFAULT_CULL_DISTANCE = 8000.0  # fallback for unmatched names
HYSTERESIS_FACTOR = 1.3
UPDATE_INTERVAL = 0.5           # seconds (2 Hz)
MAX_CHANGES_PER_TICK = 30


@dataclass
class TrackedLight:
    path: str
    wx: float
    wz: float
    cull_dist_sq: float
    hide_dist_sq: float
    visible: bool = True


def _cull_distance_for_name(name: str) -> float:
    for prefix, dist in GROUP_DISTANCES:
        if name.startswith(prefix):
            return dist
    return DEFAULT_CULL_DISTANCE


class LightCullingManager:
    """Discovers lights, then runs a 2 Hz async loop toggling visibility."""

    def __init__(self, player_location_service):
        self._pls = player_location_service
        self._lights: List[TrackedLight] = []
        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ── Discovery ────────────────────────────────────────────────────

    def discover(self) -> int:
        """Traverse the composed stage and collect all cullable lights.

        Returns the number of tracked lights.
        """
        import omni.usd
        from pxr import Usd, UsdGeom, UsdLux

        stage = omni.usd.get_context().get_stage()
        if not stage:
            print("[light_culling] no stage — discovery skipped")
            return 0

        xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        self._lights.clear()

        for prim in stage.Traverse():
            if not prim.HasAPI(UsdLux.LightAPI):
                continue
            if prim.IsA(UsdLux.DomeLight) or prim.IsA(UsdLux.DistantLight):
                continue

            try:
                m = xform_cache.GetLocalToWorldTransform(prim)
                t = m.ExtractTranslation()
                wx, wz = float(t[0]), float(t[2])
            except Exception:
                continue

            # Per-light override via USD attribute
            cull_dist = DEFAULT_CULL_DISTANCE
            override_attr = prim.GetAttribute("app:cull:distance")
            if override_attr and override_attr.HasValue():
                cull_dist = float(override_attr.Get())
            else:
                cull_dist = _cull_distance_for_name(prim.GetName())

            cull_sq = cull_dist * cull_dist
            hide_sq = (cull_dist * HYSTERESIS_FACTOR) ** 2

            self._lights.append(TrackedLight(
                path=str(prim.GetPath()),
                wx=wx,
                wz=wz,
                cull_dist_sq=cull_sq,
                hide_dist_sq=hide_sq,
            ))

        print(f"[light_culling] discovered {len(self._lights)} cullable lights")
        return len(self._lights)

    # ── Async loop ───────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._run())
        print("[light_culling] culling loop started")

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._restore_all()
        print("[light_culling] culling loop stopped, all lights restored")

    async def _run(self) -> None:
        try:
            while self._running:
                self._update_visibility()
                await asyncio.sleep(UPDATE_INTERVAL)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[light_culling] loop error: {e}")

    # ── Core update ──────────────────────────────────────────────────

    def _update_visibility(self) -> None:
        if not self._lights:
            return

        pos = self._pls.get_player_world_position() if self._pls else None
        if pos is None:
            return

        px, pz = float(pos[0]), float(pos[2])

        to_show: list = []
        to_hide: list = []

        for lt in self._lights:
            dx = lt.wx - px
            dz = lt.wz - pz
            dist_sq = dx * dx + dz * dz

            if lt.visible and dist_sq > lt.hide_dist_sq:
                to_hide.append(lt)
            elif not lt.visible and dist_sq <= lt.cull_dist_sq:
                to_show.append(lt)

        # Prioritise showing lights over hiding (avoids visible darkness)
        changes = to_show[:MAX_CHANGES_PER_TICK]
        remaining = MAX_CHANGES_PER_TICK - len(changes)
        if remaining > 0:
            changes.extend(to_hide[:remaining])

        if not changes:
            return

        self._apply_changes(changes, to_show_set=set(id(lt) for lt in to_show))

    def _apply_changes(self, changes: list, to_show_set: set) -> None:
        try:
            import omni.usd
            from pxr import Sdf, Usd, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                with Sdf.ChangeBlock():
                    for lt in changes:
                        prim = stage.GetPrimAtPath(lt.path)
                        if not prim or not prim.IsValid():
                            continue
                        img = UsdGeom.Imageable(prim)
                        if id(lt) in to_show_set:
                            img.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
                            lt.visible = True
                        else:
                            img.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                            lt.visible = False
        except Exception as e:
            print(f"[light_culling] apply error: {e}")

    # ── Shutdown restore ─────────────────────────────────────────────

    def _restore_all(self) -> None:
        """Make every tracked light visible again (clean shutdown)."""
        hidden = [lt for lt in self._lights if not lt.visible]
        if not hidden:
            return
        try:
            import omni.usd
            from pxr import Sdf, Usd, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                with Sdf.ChangeBlock():
                    for lt in hidden:
                        prim = stage.GetPrimAtPath(lt.path)
                        if not prim or not prim.IsValid():
                            continue
                        UsdGeom.Imageable(prim).GetVisibilityAttr().Set(
                            UsdGeom.Tokens.inherited
                        )
                        lt.visible = True
            print(f"[light_culling] restored {len(hidden)} lights to visible")
        except Exception as e:
            print(f"[light_culling] restore error: {e}")
