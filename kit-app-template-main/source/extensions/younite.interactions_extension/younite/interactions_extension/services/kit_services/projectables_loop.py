"""Per-frame projectable overlay pipeline.

Each tick: resolve the world position of every projectable interaction
point, apply range gating (radius / radiusMeters), adjust the display
anchor for speech-bubble / NPC-pointer styles, project to screen pixels,
and dispatch a single ``uiInteractionBoxesUpdate`` event to the frontend.

The loop injects a player-location marker when the first-person camera
has a valid last-known position (the web side filters visibility based
on the active camera).

The loop is independently throttled (``min_interval_ms``) and also skips
empty updates unless the previous frame had items, avoiding empty-pump
traffic to the WebRTC data channel.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from ... import usd_helpers


class ProjectablesLoop:
    """Resolve projectable points, project to screen, and dispatch."""

    def __init__(
        self,
        *,
        projection_service,
        get_player_pos: Callable[[], Optional[Tuple[float, float, float]]],
        update_event_name: str,
        min_interval_ms: int,
    ):
        self._projection = projection_service
        self._get_player_pos = get_player_pos
        self._update_event_name = update_event_name
        self._min_interval_ms = int(min_interval_ms)
        self._last_sent_ms: int = 0
        self._last_items_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def min_interval_ms(self) -> int:
        return self._min_interval_ms

    @min_interval_ms.setter
    def min_interval_ms(self, v: int) -> None:
        self._min_interval_ms = int(v)

    def clear_sent(self) -> None:
        """Emit one empty payload and reset counters.

        Used when auto-move starts, so any lingering overlays disappear
        immediately without waiting for the next throttled tick.
        """
        try:
            import carb.eventdispatcher

            carb.eventdispatcher.get_eventdispatcher().dispatch_event(
                self._update_event_name,
                {"timestampMs": self._now_ms(), "viewport": None, "items": []},
            )
            self._last_items_count = 0
        except Exception:
            pass

    def reset(self) -> None:
        """Reset internal bookkeeping without emitting an event.

        Used on stage open; the next tick will start from a clean slate
        regardless of what was sent for the previous stage.
        """
        self._last_sent_ms = 0
        self._last_items_count = 0

    def tick(
        self,
        *,
        now_ms: int,
        stage,
        viewport_api,
        usd_context,
        projectable_points: list,
    ) -> None:
        if not projectable_points:
            return
        if not stage or not viewport_api:
            return

        if (now_ms - int(self._last_sent_ms)) < int(self._min_interval_ms):
            return
        self._last_sent_ms = now_ms

        meters_per_unit = usd_helpers.get_stage_meters_per_unit(stage)
        player_pos = self._get_player_pos()

        items: list = []
        for pt in projectable_points:
            item = self._project_point(
                pt=pt,
                stage=stage,
                viewport_api=viewport_api,
                usd_context=usd_context,
                meters_per_unit=meters_per_unit,
                player_pos=player_pos,
            )
            if item is not None:
                items.append(item)

        self._maybe_inject_player_marker(items=items, viewport_api=viewport_api, usd_context=usd_context)

        prev_count = int(self._last_items_count or 0)
        if not items and prev_count == 0:
            return
        self._last_items_count = len(items)

        try:
            import carb.eventdispatcher as ed

            res = self._projection._get_viewport_resolution(viewport_api)
            payload = {
                "timestampMs": now_ms,
                "viewport": {"width": int(res[0]), "height": int(res[1])} if res else None,
                "items": items,
            }
            ed.get_eventdispatcher().dispatch_event(self._update_event_name, payload)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _project_point(
        self,
        *,
        pt: dict,
        stage,
        viewport_api,
        usd_context,
        meters_per_unit: float,
        player_pos,
    ) -> Optional[dict]:
        try:
            _id = str(pt.get("id") or "").strip()
            if not _id:
                return None

            pos_cfg = pt.get("position") or {}
            pos_type = str(pos_cfg.get("type") or "xform")

            world = None
            prim_path: Optional[str] = None
            if pos_type == "xform":
                prim_path = usd_helpers.resolve_prim_path_from_config(pos_cfg)
                if prim_path:
                    world = self._projection.get_anchor_world(stage, prim_path)
            elif pos_type == "coordinates":
                coords = pos_cfg.get("coordinates")
                if isinstance(coords, (list, tuple)) and len(coords) >= 3:
                    world = (float(coords[0]), float(coords[1]), float(coords[2]))
                    prim_path = f"/VirtualInteractions/{_id}"
            if world is None:
                return None

            offset = pos_cfg.get("positionOffset")
            if isinstance(offset, (list, tuple)) and len(offset) >= 3:
                world = (
                    world[0] + float(offset[0]),
                    world[1] + float(offset[1]),
                    world[2] + float(offset[2]),
                )

            # Range gating uses the prim root position.
            trigger_cfg = pt.get("trigger") or {}
            r_meters = trigger_cfg.get("radiusMeters")
            r_units = trigger_cfg.get("radius")
            if r_meters is not None and player_pos is not None:
                dx = float(world[0]) - float(player_pos[0])
                dy = float(world[1]) - float(player_pos[1])
                dz = float(world[2]) - float(player_pos[2])
                dist_units = (dx * dx + dy * dy + dz * dz) ** 0.5
                dist_m = float(dist_units) * float(meters_per_unit)
                if dist_m > float(r_meters):
                    return None
            elif r_units is not None and player_pos is not None:
                dx = float(world[0]) - float(player_pos[0])
                dy = float(world[1]) - float(player_pos[1])
                dz = float(world[2]) - float(player_pos[2])
                dist_units = (dx * dx + dy * dy + dz * dz) ** 0.5
                if dist_units > float(r_units):
                    return None

            # After range gating, adjust anchor for display styles that anchor
            # above the Collider (speechBubble and NPC pointer).
            ui_style = ""
            for b in (pt.get("behaviors") or []):
                if isinstance(b, dict) and b.get("type") == "projectable":
                    ui_style = str((b.get("ui") or {}).get("style") or "")
                    break
            if ui_style == "speechBubble" and prim_path:
                top = usd_helpers.resolve_prim_top(prim_path)
                if top is not None:
                    world = top

            is_npc_pointer = bool(pt.get("_npc_pointer"))
            if is_npc_pointer and prim_path:
                top = usd_helpers.resolve_prim_top(prim_path)
                if top is not None:
                    world = top
                collider_visible = self._projection.is_collider_visible(
                    prim_path=prim_path, viewport_api=viewport_api, usd_context=usd_context,
                )
                if not collider_visible:
                    return None
                screen, _in_view = self._projection.world_to_screen(
                    world=world, viewport_api=viewport_api, usd_context=usd_context,
                )
                if screen is None:
                    return None
            else:
                screen, in_view = self._projection.world_to_screen(
                    world=world, viewport_api=viewport_api, usd_context=usd_context,
                )
                if not in_view or screen is None:
                    return None

            ui: dict = {}
            for b in (pt.get("behaviors") or []):
                if isinstance(b, dict) and b.get("type") == "projectable" and isinstance(b.get("ui"), dict):
                    ui = b["ui"]
                    break

            return {
                "id": _id,
                "path": prim_path or f"/VirtualInteractions/{_id}",
                "world": {"x": float(world[0]), "y": float(world[1]), "z": float(world[2])},
                "screen": {"x": int(screen[0]), "y": int(screen[1])},
                "inView": True,
                "ui": dict(ui or {}),
            }
        except Exception:
            return None

    def _maybe_inject_player_marker(self, *, items: list, viewport_api, usd_context) -> None:
        """Inject the first-person player-location marker at the start of ``items``.

        Web side filters visibility based on the currently active camera.
        Heading (``ui.headingDeg``) is added when computable so the web overlay
        can rotate the arrow icon to match the direction the player was facing.
        """
        try:
            import carb

            s = carb.settings.get_settings()
            if not s.get("/younite/player/lastFpPosValid"):
                return
            fpx = float(s.get("/younite/player/lastFpPosX") or 0)
            fpy = float(s.get("/younite/player/lastFpPosY") or 0)
            fpz = float(s.get("/younite/player/lastFpPosZ") or 0)
            fp_screen, fp_in_view = self._projection.world_to_screen(
                world=(fpx, fpy, fpz), viewport_api=viewport_api, usd_context=usd_context,
            )
            if fp_screen is None or not fp_in_view:
                return

            ui: dict = {"style": "userLocation", "title": ""}
            heading_deg = self._compute_player_marker_heading_deg(
                settings=s,
                fp_pos=(fpx, fpy, fpz),
                fp_screen=fp_screen,
                viewport_api=viewport_api,
                usd_context=usd_context,
            )
            if heading_deg is not None:
                ui["headingDeg"] = heading_deg

            items.insert(0, {
                "id": "player_location_marker",
                "path": "/VirtualInteractions/player_location_marker",
                "world": {"x": fpx, "y": fpy, "z": fpz},
                "screen": {"x": int(fp_screen[0]), "y": int(fp_screen[1])},
                "inView": True,
                "ui": ui,
            })
        except Exception:
            pass

    # On-screen heading helper ------------------------------------------------
    # USD units offset along the player's horizontal forward used to project a
    # second screen point and derive the on-screen rotation. 100 units ≈ 1 m
    # for typical stages — large enough for numerical stability, small enough
    # that perspective skew on the heading is negligible at bird's-eye altitude.
    _PLAYER_FORWARD_OFFSET_UNITS = 100.0

    def _compute_player_marker_heading_deg(
        self,
        *,
        settings,
        fp_pos: Tuple[float, float, float],
        fp_screen,
        viewport_api,
        usd_context,
    ) -> Optional[float]:
        """Return the player's horizontal look direction as a CSS rotation angle.

        Composes body + camera rotation (camera is parented under body) from
        carb-stored Euler angles, drops the Y (up) component to get a pure
        horizontal forward, projects an offset point to screen, and returns
        ``atan2(dx, -dy)`` so 0° = screen-up and positive = clockwise — the
        convention used by CSS ``transform: rotate()``.

        Note: in this kit's FP controller the body rotation is typically
        ``(0, 0, 0)`` and the look yaw lives on ``camRotY``. Composing both
        keeps us correct if the controller ever rotates the body too.
        """
        try:
            import math
            from pxr import Gf

            body_rot_x = float(settings.get("/younite/player/lastFpBodyRotX") or 0.0)
            body_rot_y = float(settings.get("/younite/player/lastFpBodyRotY") or 0.0)
            body_rot_z = float(settings.get("/younite/player/lastFpBodyRotZ") or 0.0)
            cam_rot_x = float(settings.get("/younite/player/lastFpCamRotX") or 0.0)
            cam_rot_y = float(settings.get("/younite/player/lastFpCamRotY") or 0.0)

            body_rot = (
                Gf.Rotation(Gf.Vec3d.XAxis(), body_rot_x)
                * Gf.Rotation(Gf.Vec3d.YAxis(), body_rot_y)
                * Gf.Rotation(Gf.Vec3d.ZAxis(), body_rot_z)
            )
            cam_rot = (
                Gf.Rotation(Gf.Vec3d.XAxis(), cam_rot_x)
                * Gf.Rotation(Gf.Vec3d.YAxis(), cam_rot_y)
            )
            fwd_world = (cam_rot * body_rot).TransformDir(Gf.Vec3d(0.0, 0.0, -1.0))

            fwd_x = float(fwd_world[0])
            fwd_z = float(fwd_world[2])
            horiz_len = math.hypot(fwd_x, fwd_z)
            if horiz_len <= 1e-6:
                return None
            fwd_x /= horiz_len
            fwd_z /= horiz_len

            offset = self._PLAYER_FORWARD_OFFSET_UNITS
            fwd_world_pt = (
                fp_pos[0] + fwd_x * offset,
                fp_pos[1],  # horizontal heading only — keep Y (up) unchanged
                fp_pos[2] + fwd_z * offset,
            )
            fwd_screen, _ = self._projection.world_to_screen(
                world=fwd_world_pt, viewport_api=viewport_api, usd_context=usd_context,
            )
            if fwd_screen is None:
                return None

            dx = float(fwd_screen[0]) - float(fp_screen[0])
            dy = float(fwd_screen[1]) - float(fp_screen[1])
            if (dx * dx + dy * dy) <= 1e-4:
                return None
            return float(math.degrees(math.atan2(dx, -dy)))
        except Exception:
            return None

    @staticmethod
    def _now_ms() -> int:
        try:
            import time

            return int(time.time() * 1000)
        except Exception:
            return 0
