"""Bird-eye pin service — Events 2.0 wiring and pick / teleport / dismiss flow."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from .constants import MAX_MAGNET_SNAP_XZ_CM
from .labels import spawn_point_label, waypoint_label
from .magnets import nearest_magnet_with_xz_dist2
from .osm import BirdEyePinOsmSnap
from .projector import clear_pin_overlay_state, push_pin_marker
from .sheet import dispatch_pin_error, dispatch_pin_sheet


class BirdEyePinService:
    """Subscribes to pick / teleport / dismiss; delegates magnets and OSM to helpers."""

    def __init__(self, *, mode_cache: Any, route_projector: Any = None):
        self._mode_cache = mode_cache
        self._route_projector = route_projector
        self._subs: List[Any] = []
        self._osm = BirdEyePinOsmSnap(mode_cache)

    def start(self) -> None:
        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import register_outbound_events

            register_outbound_events(["birdEyePinSheet", "birdEyePinError"])

            ed = carb.eventdispatcher.get_eventdispatcher()

            for evt_name in ("younite.pick.result", "pinTeleport", "birdEyePinDismiss"):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(evt_name), evt_name
                    )
                except Exception:
                    pass

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/bird_eye_pin_service/pick_result",
                    event_name="younite.pick.result",
                    on_event=self._on_pick_result,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/bird_eye_pin_service/pin_teleport",
                    event_name="pinTeleport",
                    on_event=self._on_pin_teleport,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.navmesh_route_extension/bird_eye_pin_service/pin_dismiss",
                    event_name="birdEyePinDismiss",
                    on_event=self._on_pin_dismiss,
                    order=0,
                )
            )
        except Exception as e:
            print(f"[bird_eye_pin] subscribe failed: {e}")

    def stop(self) -> None:
        self._subs.clear()

    def _on_pin_dismiss(self, _evt) -> None:
        clear_pin_overlay_state(self._route_projector)

    def _on_pin_teleport(self, evt) -> None:
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            try:
                x = float(payload.get("x"))
                y = float(payload.get("y"))
                z = float(payload.get("z"))
            except (TypeError, ValueError):
                print("[bird_eye_pin] pinTeleport: invalid coordinates")
                return

            try:
                from younite.usd_viewer_stage_core_extension.teleport_registry import get_teleport_service

                tp = get_teleport_service()
                if not tp:
                    print("[bird_eye_pin] pinTeleport: TeleportService unavailable")
                    return
                ok = tp.teleport_to_coordinates(x, y, z)
                if not ok:
                    print("[bird_eye_pin] pinTeleport: teleport_to_coordinates returned False")
            except Exception as e:
                print(f"[bird_eye_pin] pinTeleport failed: {e}")
        except Exception as e:
            print(f"[bird_eye_pin] pinTeleport handler crashed: {e}")

    def _on_pick_result(self, evt) -> None:
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            if str(payload.get("intent") or "") != "birdEyePin":
                return

            hit = payload.get("hit")
            if not isinstance(hit, dict):
                dispatch_pin_error("No 3D hit under that click.")
                return

            world = hit.get("world") or {}
            try:
                x = float(world.get("x"))
                y = float(world.get("y"))
                z = float(world.get("z"))
            except (TypeError, ValueError):
                dispatch_pin_error("Pick returned an invalid world position.")
                return

            click_world = (x, y, z)
            clear_pin_overlay_state(self._route_projector)

            found = nearest_magnet_with_xz_dist2(click_world)
            max_r2 = MAX_MAGNET_SNAP_XZ_CM * MAX_MAGNET_SNAP_XZ_CM
            if found is not None:
                name, pos, is_spawn, xz_d2 = found
                if xz_d2 <= max_r2:
                    self._emit_magnet_pin(name, pos, is_spawn)
                else:
                    self._handle_outside(click_world)
            else:
                self._handle_outside(click_world)
        except Exception as e:
            print(f"[bird_eye_pin] pick result handler failed: {e}")
            dispatch_pin_error("Pin service failed while handling the click.")

    def _emit_magnet_pin(
        self,
        name: str,
        pos: Tuple[float, float, float],
        is_spawn: bool,
    ) -> None:
        title = spawn_point_label(name) if is_spawn else waypoint_label(name)
        spawn_point = name if is_spawn else ""
        push_pin_marker(self._route_projector, pos)
        dispatch_pin_sheet(
            world=pos,
            title=title,
            spawn_point=spawn_point,
            magnet_name=name,
            is_inside=True,
        )

    def _handle_outside(self, click_world: Tuple[float, float, float]) -> None:
        snapped: Optional[Tuple[float, float, float]] = self._osm.snap_click(click_world)
        if snapped is None:
            dispatch_pin_error(
                "OSM road network unavailable — outside-NavMesh pinning is offline.",
            )
            return

        push_pin_marker(self._route_projector, snapped)
        dispatch_pin_sheet(
            world=snapped,
            title="Pinned location",
            spawn_point="",
            magnet_name="",
            is_inside=False,
        )
