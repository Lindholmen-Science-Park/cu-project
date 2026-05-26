"""Routes viewport pick responses to registered clickables.

Receives ``younite.pick.response`` payloads, walks the hit prim path up the
hierarchy (``/World/Red/Collider`` → ``/World/Red``) to find a registered
click entry, and then dispatches either a deferred approach (walk first,
act on arrival) or the configured onClick actions immediately.

Side-effects the router coordinates:

* NPC face-player rotation on initial click and again on arrival.
* Showing / hiding the 3D tetrahedron marker above the clicked target.
* Cancelling any pending approach whenever a new pick arrives.
* Forwarding free-space ground clicks to the navigation pipeline when
  ``allowNavigation`` is set.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ... import usd_helpers

NAV_REQUEST_EVENT = "younite.navigation.requestPoint"
OSM_ROUTE_OVERLAY_CLICK_EVENT = "younite.osm_route_overlay.click"

# Prim-path prefix of the dev OSM route overlay mesh. Any pick that
# resolves to a child of this root is intrinsically an OSM route
# overlay click — we route it through the dedicated OSM channel even
# when the web sent the generic ``pointClick`` intent (e.g. when the
# web's ``osmRouteOverlayActive`` flag is out of sync with the
# Kit-side overlay). Without this, route-overlay hits silently fall
# through to the NavMesh route engine and the user sees the route
# composer fight the direct-dispatch polyline produced by
# ``OsmRouteOverlayService``.
OSM_ROUTE_OVERLAY_PRIM_PREFIX = "/World/OsmRouteDevOverlay"


class ClickRouter:
    """Translate pick hits into click actions or approach-then-act sequences."""

    def __init__(
        self,
        *,
        action_handler,
        approach_service,
        marker_service,
        rotation_service,
        get_player_pos: Callable[[], Optional[tuple]],
        get_click_points_by_path: Callable[[], dict],
    ):
        self._actions = action_handler
        self._approach = approach_service
        self._marker = marker_service
        self._rotation = rotation_service
        self._get_player_pos = get_player_pos
        self._get_click_points_by_path = get_click_points_by_path

    # ------------------------------------------------------------------
    # Pick-response handler
    # ------------------------------------------------------------------

    def handle_pick_response(self, payload: dict) -> None:
        intent = str(payload.get("intent") or "")
        if intent not in ("pointClick", "osmRouteOverlayMarker"):
            return

        # A new click always cancels any pending approach.
        try:
            if self._approach:
                self._approach.cancel()
        except Exception:
            pass

        hit = payload.get("hit") or {}
        if not isinstance(hit, dict):
            hit = {}
        prim_path = str(
            hit.get("primPath")
            or hit.get("collider")
            or hit.get("colliderPrimPath")
            or hit.get("bodyPrimPath")
            or ""
        ).strip()

        clickable, matched_path = self._resolve_clickable(prim_path)

        world = self._extract_world_coord(hit)

        if clickable:
            self._execute_clickable(clickable, matched_path or prim_path)
            return

        # Free-space ground click — optionally forward to navigation.
        try:
            self._marker.show()
        except Exception:
            pass

        allow_nav = bool(payload.get("allowNavigation", False)) or intent == "osmRouteOverlayMarker"
        if world is not None and allow_nav:
            prim_path = str(
                hit.get("primPath")
                or hit.get("colliderPrimPath")
                or hit.get("bodyPrimPath")
                or ""
            ).strip()
            # OSM route-overlay hits always go through the OSM channel,
            # regardless of which intent the web actually sent. A click
            # that landed on the visible overlay must engage the
            # direct-dispatch route traversal, not the NavMesh route
            # engine — otherwise the engine's composer-built path will
            # race with (and clobber) the polyline OsmRouteOverlayService
            # is feeding the auto-mover.
            on_osm_route_overlay = bool(
                prim_path and prim_path.startswith(OSM_ROUTE_OVERLAY_PRIM_PREFIX)
            )
            if intent == "osmRouteOverlayMarker" or on_osm_route_overlay:
                self._dispatch_osm_route_overlay_click(world, prim_path)
            else:
                self._dispatch_nav_request(world, prim_path)

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _resolve_clickable(self, prim_path: str):
        """Walk up the prim path until a registered clickable is found."""
        if not prim_path:
            return None, ""
        by_path = self._get_click_points_by_path() or {}
        probe = prim_path
        while probe:
            if probe in by_path:
                return by_path.get(probe), probe
            if probe == "/":
                break
            if "/" not in probe.strip("/"):
                probe = "/"
            else:
                probe = probe.rsplit("/", 1)[0] or "/"
        return None, ""

    @staticmethod
    def _extract_world_coord(hit: dict):
        try:
            w = hit.get("world") if isinstance(hit, dict) else None
            if isinstance(w, dict):
                return (float(w.get("x")), float(w.get("y")), float(w.get("z")))
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Clickable execution
    # ------------------------------------------------------------------

    def _execute_clickable(self, clickable: dict, matched_path: str) -> None:
        interactable_id = str(clickable.get("id") or matched_path or "clickable")

        actions: List[Dict[str, Any]] = []
        try:
            for b in (clickable.get("behaviors") or []):
                if isinstance(b, dict) and b.get("type") == "action":
                    actions.extend(list(((b.get("actions") or {}).get("onClick") or [])))
        except Exception:
            actions = []

        is_npc = str(clickable.get("interactionType") or "") == "npc"

        # NPCs: keep the marker hidden; icons / others: keep it shown.
        try:
            if is_npc:
                self._marker.hide()
            else:
                self._marker.show()
        except Exception:
            pass

        click_prim = usd_helpers.resolve_prim_path_from_config(clickable.get("position") or {})
        player_pos = self._get_player_pos()

        # NPCs: rotate to face the player on initial click.
        if is_npc and click_prim and player_pos:
            self._rotation.start_rotation_toward(click_prim, player_pos)

        approach_cfg = clickable.get("approach")
        if isinstance(approach_cfg, dict) and click_prim:
            distance_m = float(approach_cfg.get("distanceMeters", 3.0) or 3.0)
            target_world = usd_helpers.resolve_prim_position(click_prim)
            if target_world and self._approach:
                iid = interactable_id
                acts = list(actions)
                npc_prim_for_arrival = click_prim if is_npc else None

                def _on_arrival():
                    if npc_prim_for_arrival:
                        pp = self._get_player_pos()
                        if pp:
                            self._rotation.start_rotation_toward(npc_prim_for_arrival, pp)
                    self._actions.execute_onclick(interactable_id=iid, actions=acts)

                if self._approach.request(
                    target_pos=target_world,
                    distance_meters=distance_m,
                    on_arrival=_on_arrival,
                ):
                    return

        self._actions.execute_onclick(interactable_id=interactable_id, actions=actions)

    # ------------------------------------------------------------------
    # Navigation forwarding
    # ------------------------------------------------------------------

    @staticmethod
    def _dispatch_nav_request(world, pick_prim_path: str = "") -> None:
        try:
            import carb.eventdispatcher

            evt_payload: Dict[str, Any] = {
                "world": {"x": world[0], "y": world[1], "z": world[2]},
            }
            if pick_prim_path:
                evt_payload["pickPrimPath"] = pick_prim_path
            carb.eventdispatcher.get_eventdispatcher().dispatch_event(
                NAV_REQUEST_EVENT,
                evt_payload,
            )
        except Exception:
            pass

    @staticmethod
    def _dispatch_osm_route_overlay_click(world, pick_prim_path: str = "") -> None:
        """Dispatch a dedicated OSM route overlay click event
        (intercepted by ``OsmRouteOverlayService``).

        We use a separate event channel — instead of dispatching
        ``younite.navigation.requestPoint`` and mutating the payload in
        flight — because carb event payloads are read-only views in
        Kit 110+, so observers cannot reliably edit a request before it
        reaches the next observer. The OSM service handles the snap
        itself and re-emits a clean nav request.
        """
        try:
            import carb.eventdispatcher

            evt_payload: Dict[str, Any] = {
                "world": {"x": world[0], "y": world[1], "z": world[2]},
            }
            if pick_prim_path:
                evt_payload["pickPrimPath"] = pick_prim_path
            carb.eventdispatcher.get_eventdispatcher().dispatch_event(
                OSM_ROUTE_OVERLAY_CLICK_EVENT,
                evt_payload,
            )
        except Exception:
            pass
