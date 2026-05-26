"""
View switching: first-person entry + non-FP view transitions.

Owns:

* The ``_fp_enter_lock`` that serializes FP entry against chat's
  triple-event burst (``chat.moveToSpawnpoint`` /
  ``chat.moveAccepted`` / ``teleportToSpawnpoint`` can all fire in
  quick succession and would otherwise interleave LOD switches and
  navmesh prep calls).
* The ``firstPerson`` and ``birdsEye`` / other view transition async
  primitives used by every entry point (view-switch button, spawn
  teleport, directions flows).
* The synchronous event handlers that kick those primitives off
  (``cameraViewSwitchRequest``, ``teleportToSpawnpoint`` +
  ``chat.*`` aliases).

The directions handlers (``MapMarkerDirectionsHandler``,
``SeatDirectionsHandler``) call ``async_first_person_enter`` on the
orchestrator, which thin-delegates to the instance of this class —
one place to keep the "enter FP correctly" recipe (LOD switch →
navmesh prep → teleport → settle frames → optional ready dispatch).
"""
from __future__ import annotations

import asyncio
import time


# ----------------------------------------------------------------------
# Tunables
# ----------------------------------------------------------------------
#
# ``VIEW_TRANSITION_GEOMETRY_DEADLINE_SEC`` — maximum wall-clock we're
# willing to hold the black view-transition overlay waiting for the
# stadium LOD + navmesh to settle before falling back (see
# ``view_transition_readiness.await_stadium_lod_for_view_type`` and
# ``first_person_navmesh_bridge.await_first_person_navmesh_prepare``).
#
# ``STREAM_SETTLE_FRAMES`` — extra Kit ticks to let the renderer flush
# after all operations complete before dispatching ``viewTransitionReady``.
# At 30 fps this is ~130 ms of invisible delay while the screen is
# still fully black. Error paths dispatch immediately (no settle) so
# the overlay never gets stuck.

VIEW_TRANSITION_GEOMETRY_DEADLINE_SEC = 15.0
STREAM_SETTLE_FRAMES = 4


class ViewSwitcher:
    """First-person and non-FP view-switch orchestration."""

    def __init__(self, service):
        self._svc = service
        self._fp_enter_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Sync event handlers
    # ------------------------------------------------------------------

    def on_camera_view_switch(self, event) -> None:
        svc = self._svc
        try:
            if not svc.camera:
                return
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            view_type = str(payload.get("viewType", "firstPerson")).strip()

            if view_type != "firstPerson":
                # Only capture FP state when the player is *currently* in
                # first-person. Otherwise (e.g. a redundant birdEye→birdEye
                # switch from the globe view exit) we'd overwrite a valid
                # stored FP pose with the player's current bird-eye spawn
                # position, breaking wayfinding "current location" + the
                # bird-eye user-location marker.
                current_view = str(
                    getattr(svc.camera, "_current_view_type", "firstPerson") or "firstPerson"
                )
                if current_view == "firstPerson":
                    fp_snapshot = svc.fp_state.capture()
                    if fp_snapshot:
                        svc.fp_state.store(fp_snapshot)

            if svc.world_state:
                svc.world_state.set("cameraViewType", view_type)
            if view_type == "firstPerson":
                asyncio.ensure_future(self.async_first_person_enter(""))
            else:
                asyncio.ensure_future(
                    self.async_non_fp_view_switch(view_type, "")
                )
        except Exception:
            pass

    def on_player_state_capture_request(self, event) -> None:
        """Snapshot + store the player's current first-person pose without
        switching views or teleporting.

        Used by the web side when entering modes that don't go through a
        ``cameraViewSwitchRequest`` to bird-eye but still need the FP
        pose preserved (currently: dev → space globe view). Without this
        the ``_current_view_type`` guard in ``on_camera_view_switch``
        would have nothing to fall back to when the user later exits
        the globe straight into bird-eye.
        """
        svc = self._svc
        try:
            if not svc.camera:
                return
            current_view = str(
                getattr(svc.camera, "_current_view_type", "firstPerson") or "firstPerson"
            )
            if current_view != "firstPerson":
                # Same guard as on_camera_view_switch: never store a
                # non-FP pose as the FP state.
                return
            fp_snapshot = svc.fp_state.capture()
            if fp_snapshot:
                svc.fp_state.store(fp_snapshot)
        except Exception:
            pass

    def on_spawnpoint_teleport(self, event) -> None:
        svc = self._svc
        try:
            if not svc.camera:
                return
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            name = str(payload.get("spawnpointName") or "").strip()
            poi_id = str(payload.get("poiId") or "").strip()
            if not name and poi_id:
                name = f"spawnpoint_{poi_id}"
            view_type = str(payload.get("viewType") or "firstPerson").strip()
            if svc.world_state:
                svc.world_state.set("cameraViewType", view_type)
            if view_type == "firstPerson":
                asyncio.ensure_future(self.async_first_person_enter(name))
            else:
                asyncio.ensure_future(
                    self.async_non_fp_view_switch(view_type, name)
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Async primitives (reused by directions handlers via the service)
    # ------------------------------------------------------------------

    async def async_first_person_enter(
        self,
        spawn_point: str,
        *,
        dispatch_ready: bool = True,
    ) -> bool:
        """Apply FP view + LOD, wait for navmesh, then teleport.

        Serialized against chat triple-events via ``_fp_enter_lock``.

        When ``dispatch_ready`` is ``False`` the caller is responsible
        for firing ``viewTransitionReady`` itself — used by the
        bird-eye → first-person directions flows so the black overlay
        stays up until the route they kick off has actually been
        calculated (see ``await_navmesh_route_settled``). Returns
        ``True`` on success, ``False`` on failure (in which case the
        failure event was already dispatched here so the overlay never
        gets stuck).
        """
        from ....first_person_navmesh_bridge import (
            await_first_person_navmesh_prepare,
        )
        from ..view_transition_readiness import await_stadium_lod_for_view_type

        svc = self._svc
        cam = svc.camera
        async with self._fp_enter_lock:
            try:
                lod_deadline = (
                    time.monotonic() + VIEW_TRANSITION_GEOMETRY_DEADLINE_SEC
                )
                cam._apply_view_type("firstPerson")
                lod_ok = await await_stadium_lod_for_view_type(
                    "firstPerson", deadline=lod_deadline
                )
                if not lod_ok:
                    print(
                        "[feature_commands] deadline waiting for full stadium LOD before navmesh bake"
                    )
                await await_first_person_navmesh_prepare()

                stored = None if spawn_point else svc.fp_state.read()
                if stored:
                    pos = stored["pos"]
                    ts = getattr(cam, "_teleport_service", None)
                    if ts:
                        ts.teleport_to_coordinates(pos[0], pos[1], pos[2])
                    else:
                        cam.move_player_to_spawnpoint(
                            "PlayerSpawnPoint_01", apply_gravity=None
                        )
                    svc.fp_state.restore_rotation(stored)
                else:
                    target = spawn_point or "PlayerSpawnPoint_01"
                    cam.move_player_to_spawnpoint(target, apply_gravity=None)

                svc.fp_state.store(None)

                import omni.kit.app as kit_app

                for _ in range(STREAM_SETTLE_FRAMES):
                    await kit_app.get_app().next_update_async()

                if dispatch_ready:
                    svc.dispatch_view_transition_ready(
                        "firstPerson", True, "", spawn_point=spawn_point or ""
                    )
                return True
            except Exception as e:
                # Always dispatch on exception so the web overlay never
                # hangs, even when the caller asked us to defer the
                # ready signal.
                svc.dispatch_view_transition_ready(
                    "firstPerson",
                    False,
                    str(e),
                    spawn_point=spawn_point or "",
                )
                return False

    async def async_non_fp_view_switch(
        self, view_type: str, spawn_point: str
    ) -> None:
        """Switch to a non-FP view (e.g. bird's-eye) + teleport; fade-in after LOD predicate."""
        from ..view_transition_readiness import await_view_transition_scene_ready

        svc = self._svc
        try:
            if spawn_point:
                ok = svc.camera.switch_camera_view(view_type, spawn_point=spawn_point)
            else:
                ok = svc.camera.switch_camera_view(view_type)
        except Exception as e:
            svc.dispatch_view_transition_ready(
                view_type, False, str(e), spawn_point=spawn_point or ""
            )
            return

        deadline = time.monotonic() + VIEW_TRANSITION_GEOMETRY_DEADLINE_SEC
        await await_view_transition_scene_ready(view_type, deadline=deadline)

        import omni.kit.app as kit_app

        for _ in range(STREAM_SETTLE_FRAMES):
            await kit_app.get_app().next_update_async()

        svc.dispatch_view_transition_ready(
            view_type,
            bool(ok),
            "" if ok else "camera switch failed",
            spawn_point=spawn_point or "",
        )


__all__ = [
    "ViewSwitcher",
    "VIEW_TRANSITION_GEOMETRY_DEADLINE_SEC",
    "STREAM_SETTLE_FRAMES",
]
