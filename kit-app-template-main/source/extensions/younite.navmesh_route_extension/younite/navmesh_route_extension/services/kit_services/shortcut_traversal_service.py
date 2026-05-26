"""
Shortcut traversal service — fade + teleport + resume.

Listens for ``playerPathClassChange`` events emitted by the
PointClickAutoMover and intercepts the moment the player enters a
``"shortcut"``-class polyline segment (the entrance vertex of an
elevator hop produced by ``RouteComposer._try_shortcut_route``).

When intercepted:

1. The auto-mover is paused via ``autoMoveStatus`` (``active=false``).
2. ``shortcutTraversalBegin`` is dispatched to the web frontend. The
   frontend calls ``beginViewTransition`` to fade the screen to black
   and, when its fade-out animation completes, sends
   ``shortcutTraversalProceed`` back to Kit (mirrors the
   ``onFadeOutComplete`` → ``sendMessage`` pattern used by the seat /
   POI teleport flows in :file:`useNavmeshCore.ts`).
3. On ``shortcutTraversalProceed`` (or a ``_FADE_TIMEOUT`` safety cap
   if the frontend never replies — e.g. dev session without the
   handler wired up) the player is moved to the exit Xform via
   ``TeleportService.teleport_to_coordinates``.
4. After a short settle, ``viewTransitionReady`` is dispatched
   (frontend fades back in) followed by ``shortcutTraversalComplete``
   so any UI hooks observing the traversal lifecycle can react.
5. The route is recomposed from the new player position so auto-move
   continues to the original destination — the freshly-computed leg
   does not include the same shortcut (composer prefers direct walking
   when the player is already on the destination floor).

Notes:

* This service is the *only* component that performs the teleport for a
  shortcut hop. The composer marks the segment with
  ``segment_classes[i] = "shortcut"`` and a near-zero speed multiplier;
  the auto-mover never walks meaningful distance through it before this
  service catches the transition. The near-zero speed is a defensive
  fallback in case the service is missing — the player crawls at ~30
  cm/s rather than zipping through walls or deadlocking.
* Per-route guard: ``_busy_routes`` prevents re-entrancy if the
  auto-mover re-emits the transition during a slow recompute.
"""
from __future__ import annotations

import asyncio
import math
from typing import Dict, List, Optional, Tuple

import omni.kit.app as kit_app


_FADE_TIMEOUT_SEC = 1.5
_FADE_BACK_DELAY_SEC = 0.2


class ShortcutTraversalService:
    """Owns the fade/teleport/resume lifecycle for shortcut hops."""

    def __init__(
        self,
        *,
        get_router,
        get_route_service,
    ) -> None:
        self._get_router = get_router
        self._get_route_service = get_route_service
        self._subs: List[object] = []
        self._busy_routes: Dict[str, bool] = {}
        self._proceed_events: Dict[str, asyncio.Event] = {}

    # ────────────────────────────────────────────────────────────
    # Lifecycle
    # ────────────────────────────────────────────────────────────

    def start(self) -> None:
        try:
            import carb
            import carb.eventdispatcher
        except Exception as exc:
            print(f"[shortcut_traversal] cannot subscribe (no eventdispatcher): {exc}")
            return
        try:
            from younite.messaging_core_extension.message_utils import (
                register_outbound_events,
            )

            register_outbound_events([
                "shortcutTraversalBegin",
                "shortcutTraversalComplete",
                "shortcutTraversalError",
            ])
        except Exception:
            pass

        ed = carb.eventdispatcher.get_eventdispatcher()

        def _alias(name: str) -> None:
            try:
                kit_app.register_event_alias(carb.events.type_from_string(name), name)
            except Exception:
                pass

        def _observe(name: str, handler) -> None:
            _alias(name)
            self._subs.append(
                ed.observe_event(
                    observer_name=f"younite.shortcut_traversal/{name}",
                    event_name=name,
                    on_event=handler,
                    order=0,
                )
            )

        _observe("playerPathClassChange", self._on_path_class_change)
        _observe("shortcutTraversalProceed", self._on_proceed)

    def stop(self) -> None:
        self._subs.clear()
        self._busy_routes.clear()
        self._proceed_events.clear()

    # ────────────────────────────────────────────────────────────
    # Event handlers
    # ────────────────────────────────────────────────────────────

    def _on_path_class_change(self, evt) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )
        except Exception:
            return
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        nxt = str(payload.get("next") or "")
        if nxt != "shortcut":
            return
        route_id = str(payload.get("routeId") or "")
        if not route_id:
            return
        seg_idx = int(payload.get("segIdx") or 0)
        if self._busy_routes.get(route_id):
            return
        self._busy_routes[route_id] = True
        asyncio.ensure_future(self._traverse(route_id, seg_idx))

    def _on_proceed(self, evt) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )
        except Exception:
            return
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        route_id = str(payload.get("routeId") or "")
        ev = self._proceed_events.get(route_id)
        if ev is not None and not ev.is_set():
            try:
                ev.set()
            except Exception:
                pass

    # ────────────────────────────────────────────────────────────
    # Traversal coroutine
    # ────────────────────────────────────────────────────────────

    async def _traverse(self, route_id: str, seg_idx: int) -> None:
        try:
            ok = await self._traverse_inner(route_id, seg_idx)
            if not ok:
                self._dispatch("shortcutTraversalError", {"routeId": route_id})
        except Exception as exc:
            print(f"[shortcut_traversal] traverse failed: {exc}")
            self._dispatch("shortcutTraversalError", {"routeId": route_id, "error": str(exc)})
        finally:
            self._busy_routes.pop(route_id, None)

    async def _traverse_inner(self, route_id: str, seg_idx: int) -> bool:
        svc = self._get_route_service() if callable(self._get_route_service) else None
        if svc is None:
            print("[shortcut_traversal] no route service")
            return False
        route = svc._routes.get(route_id)
        if route is None:
            return False

        polyline = route.get_last_path_points()
        classes = list(getattr(route, "_last_segment_classes", []) or [])
        if seg_idx < 0 or seg_idx >= len(classes):
            print(
                f"[shortcut_traversal] seg_idx {seg_idx} out of range "
                f"(len={len(classes)})"
            )
            return False
        if classes[seg_idx] != "shortcut":
            return False
        if seg_idx + 1 >= len(polyline):
            return False
        entrance = polyline[seg_idx]
        exit_pos = polyline[seg_idx + 1]

        # Look up rich metadata via the router (for analytics / web UI).
        meta = self._lookup_meta(entrance, exit_pos)
        original_destination = polyline[-1] if polyline else None

        self._pause_auto_move(route_id)
        proceed_event = asyncio.Event()
        self._proceed_events[route_id] = proceed_event
        self._dispatch(
            "shortcutTraversalBegin",
            {
                "routeId": route_id,
                "fromPos": [float(entrance[0]), float(entrance[1]), float(entrance[2])],
                "toPos": [float(exit_pos[0]), float(exit_pos[1]), float(exit_pos[2])],
                "groupId": (meta or {}).get("groupId"),
                "type": (meta or {}).get("type"),
                "fromLabel": (meta or {}).get("fromLabel"),
                "toLabel": (meta or {}).get("toLabel"),
                "traversalSeconds": (meta or {}).get("traversalSeconds"),
            },
        )

        # Wait for the frontend fade-out to complete (or time out — e.g.
        # the dev shortcut handler isn't wired up).
        try:
            await asyncio.wait_for(proceed_event.wait(), _FADE_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            print(
                "[shortcut_traversal] shortcutTraversalProceed timeout "
                f"({_FADE_TIMEOUT_SEC}s); proceeding to teleport"
            )
        finally:
            self._proceed_events.pop(route_id, None)

        # Perform the teleport.
        teleported = self._teleport(exit_pos)
        if not teleported:
            self._dispatch(
                "shortcutTraversalError",
                {"routeId": route_id, "error": "teleport_failed"},
            )
            # Always release the fade overlay even on failure.
            self._dispatch("viewTransitionReady", {})
            return False

        # Brief settle so the camera lands before fade-in begins.
        try:
            for _ in range(2):
                await kit_app.get_app().next_update_async()
        except Exception:
            pass
        await asyncio.sleep(_FADE_BACK_DELAY_SEC)
        # Tell the frontend to fade back in (matches the
        # TeleportService.viewTransitionReady contract used by seat /
        # POI teleports), then signal traversal completion for any
        # downstream UI hooks.
        self._dispatch("viewTransitionReady", {})
        self._dispatch("shortcutTraversalComplete", {"routeId": route_id})

        # Resume the route from the new player position. The composer
        # reroutes from /World/PlayerCharacter (which TeleportService
        # just moved); shortcuts stay enabled but the new direct walk
        # to the destination is shorter than another elevator hop, so
        # Dijkstra returns a plain navmesh route this time.
        if original_destination is not None:
            try:
                self._resume_route(route_id, route, original_destination)
            except Exception as exc:
                print(f"[shortcut_traversal] resume failed: {exc}")
        return True

    # ────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────

    def _lookup_meta(self, entrance, exit_pos) -> Optional[dict]:
        """Best-effort metadata lookup — match nodes by world position."""
        router = self._get_router() if callable(self._get_router) else None
        if router is None:
            return None
        try:
            best_pair: Optional[Tuple[object, object]] = None
            best_d2 = float("inf")
            tol2 = 50.0 * 50.0
            for grp in router.get_groups():
                for n_in in grp.nodes:
                    d_in = self._sq_dist(n_in.pos, entrance)
                    if d_in > tol2:
                        continue
                    for n_out in grp.nodes:
                        if n_out is n_in:
                            continue
                        d_out = self._sq_dist(n_out.pos, exit_pos)
                        if d_out > tol2:
                            continue
                        score = d_in + d_out
                        if score < best_d2:
                            best_d2 = score
                            best_pair = (grp, n_in, n_out)
            if best_pair is None:
                return None
            grp, n_in, n_out = best_pair
            return {
                "groupId": grp.group_id,
                "type": grp.type_,
                "fromLabel": n_in.label,
                "toLabel": n_out.label,
                "traversalSeconds": grp.traversal_seconds,
            }
        except Exception:
            return None

    @staticmethod
    def _sq_dist(a, b) -> float:
        return (
            (float(a[0]) - float(b[0])) ** 2
            + (float(a[1]) - float(b[1])) ** 2
            + (float(a[2]) - float(b[2])) ** 2
        )

    def _pause_auto_move(self, route_id: str) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            dispatch_to_events2(
                "autoMoveStatus", {"routeId": route_id, "active": False},
            )
        except Exception:
            pass

    def _teleport(self, pos) -> bool:
        try:
            from younite.usd_viewer_stage_core_extension.teleport_registry import (
                get_teleport_service,
            )

            tp = get_teleport_service()
            if tp is None:
                print("[shortcut_traversal] TeleportService not available")
                return False
            return bool(
                tp.teleport_to_coordinates(
                    float(pos[0]), float(pos[1]), float(pos[2]),
                )
            )
        except Exception as exc:
            print(f"[shortcut_traversal] teleport failed: {exc}")
            return False

    def _dispatch(self, name: str, payload: dict) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            dispatch_to_events2(name, payload)
        except Exception:
            pass

    def _resume_route(self, route_id: str, route, destination) -> None:
        """Reissue the route from the player's new position (post-teleport)."""
        svc = self._get_route_service() if callable(self._get_route_service) else None
        if svc is None:
            return
        cfg = route._cfg
        was_auto = bool(getattr(route, "_auto_move_active", False))
        end_ref = (
            float(destination[0]),
            float(destination[1]),
            float(destination[2]),
        )
        svc.set_route_for_id(
            route_id,
            "/World/PlayerCharacter",
            end_ref,
            path_prim=cfg.path_prim,
            curve_width=cfg.curve_width,
            enable_periodic_recalc=cfg.enable_periodic_recalc,
            start_use_ground=cfg.start_use_ground,
            draw_path=cfg.draw_path,
            recalc_now_if_active=True,
            face_direction=False,
            via_points=[],
            corridor_section=getattr(cfg, "corridor_section", None),
            auto_move=was_auto,
            use_composer=cfg.use_composer,
        )


__all__ = ["ShortcutTraversalService"]
