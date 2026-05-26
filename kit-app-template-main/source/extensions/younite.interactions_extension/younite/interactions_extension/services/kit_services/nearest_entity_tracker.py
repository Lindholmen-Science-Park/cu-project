"""Nearest-entity proximity tracker.

Watches a registry of entities (NPCs or icons), finds the closest one to the
player each frame, and dispatches an outbound event only when the identity of
the nearest entity changes. The same class drives both NPC and icon
proximity; construction parameters select the event name, payload key
(``npcConfig`` vs ``iconConfig``), and the registry field name that holds the
config dict (``npc_config`` vs ``icon_config``).

For the **icon** tracker only, optional ``coin_poi_max_visible_m`` reuses the
same per-entry distance computed in :meth:`update` to show/hide
``mediaType: "coinPoi"`` prims via the payload orchestrator — no second
distance pass.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from ... import usd_helpers

# Default vertical tolerance for coin POI bottom-pill proximity (meters).
# Multi-floor stacks can be <4 m apart horizontally while several meters
# apart in Y; horizontal range + this cap avoids pills on the wrong floor.
_COIN_POI_DEFAULT_MAX_VERTICAL_M = 1.5


class NearestEntityTracker:
    """Dispatch ``{nearest: {...}}`` on change, ``{nearest: null}`` on clear."""

    def __init__(
        self,
        *,
        event_name: str,
        payload_key: str,
        registry_cfg_field: str,
        get_player_pos: Callable[[], Optional[Tuple[float, float, float]]],
        coin_poi_max_visible_m: Optional[float] = None,
    ):
        self._event_name = event_name
        self._payload_key = payload_key
        self._registry_cfg_field = registry_cfg_field
        self._get_player_pos = get_player_pos
        self._last_nearest_id: str = ""
        self._coin_poi_max_visible_m = coin_poi_max_visible_m
        self._coin_visibility_last: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear internal bookkeeping silently — no event is dispatched.

        Use after a fresh config load so the next real :meth:`update`
        re-evaluates against the new registry without a spurious clear.
        """
        self._last_nearest_id = ""
        self._coin_visibility_last.clear()

    def clear_and_dispatch(self) -> None:
        """If a nearest is currently set, clear it and dispatch ``nearest: null``.

        Also clears coin visibility bookkeeping so the next :meth:`update`
        re-submits orchestrator ops after interaction suspend (e.g. auto-move).
        """
        if self._last_nearest_id:
            self._last_nearest_id = ""
            self._dispatch(None)
        self._coin_visibility_last.clear()

    def update(self, registry: dict) -> None:
        coin_vis_pending: list = []

        if not registry:
            if self._last_nearest_id:
                self._last_nearest_id = ""
                self._dispatch(None)
            if self._coin_poi_max_visible_m is not None:
                self._coin_visibility_last.clear()
            return

        player_pos = self._get_player_pos()
        if player_pos is None:
            return

        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
        except Exception:
            return
        if not stage:
            return

        try:
            from pxr import Usd, UsdGeom

            xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        except Exception:
            return

        meters_per_unit = usd_helpers.get_stage_meters_per_unit(stage)
        nearest_id = ""
        nearest_dist = float("inf")
        nearest_cfg = None

        for entity_id, entry in registry.items():
            prim_path = entry.get("prim_path")
            if not prim_path:
                continue
            world = usd_helpers.resolve_prim_position(
                prim_path, stage=stage, xform_cache=xform_cache
            )
            if world is None:
                continue
            dx = float(world[0]) - float(player_pos[0])
            dy = float(world[1]) - float(player_pos[1])
            dz = float(world[2]) - float(player_pos[2])
            dist_m = ((dx * dx + dy * dy + dz * dz) ** 0.5) * meters_per_unit
            dist_xz_m = ((dx * dx + dz * dz) ** 0.5) * meters_per_unit
            vert_m = abs(dy) * meters_per_unit

            r_cfg = entry.get(self._registry_cfg_field)
            cfg_dict = r_cfg if isinstance(r_cfg, dict) else {}
            if (
                self._coin_poi_max_visible_m is not None
                and self._registry_cfg_field == "icon_config"
                and cfg_dict.get("mediaType") == "coinPoi"
            ):
                visible = dist_m <= float(self._coin_poi_max_visible_m)
                if self._coin_visibility_last.get(prim_path) != visible:
                    coin_vis_pending.append((prim_path, visible))

            radius_m = entry.get("radius_meters")
            prox_dist_m = dist_m
            if radius_m is not None:
                max_vert_m = entry.get("max_vertical_meters")
                if max_vert_m is None and cfg_dict.get("mediaType") == "coinPoi":
                    max_vert_m = _COIN_POI_DEFAULT_MAX_VERTICAL_M
                if max_vert_m is not None and vert_m > float(max_vert_m):
                    continue
                if cfg_dict.get("mediaType") == "coinPoi":
                    prox_dist_m = dist_xz_m
                if prox_dist_m > float(radius_m):
                    continue

            if prox_dist_m < nearest_dist:
                nearest_dist = prox_dist_m
                nearest_id = entity_id
                nearest_cfg = entry.get(self._registry_cfg_field)

        if coin_vis_pending:
            try:
                from younite.payload_orchestrator_core_extension import batch_show_hide, Priority

                ok = batch_show_hide(
                    coin_vis_pending,
                    Priority.MEDIUM,
                    source="interactions_coin_cull",
                    group="coin_cull",
                )
            except Exception:
                ok = False
            if ok:
                for prim_path, visible in coin_vis_pending:
                    self._coin_visibility_last[prim_path] = visible

        if nearest_id == self._last_nearest_id:
            return

        self._last_nearest_id = nearest_id

        if nearest_id and nearest_cfg:
            self._dispatch({
                "id": nearest_id,
                self._payload_key: dict(nearest_cfg),
                "distanceMeters": round(nearest_dist, 2),
            })
        else:
            self._dispatch(None)

    # ------------------------------------------------------------------

    def _dispatch(self, nearest_payload) -> None:
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2(self._event_name, {"nearest": nearest_payload})
        except Exception:
            pass
