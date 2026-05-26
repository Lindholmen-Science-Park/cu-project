from __future__ import annotations

from typing import Any, Optional


class SettingsWatchers:
    """Wires settings-backed behavior (ready gate, movement speed, view type)."""

    def __init__(self, host: Any):
        self._h = host
        self._ready_for_player_sub: Optional[Any] = None
        self._movement_speed_sub: Optional[Any] = None
        self._camera_view_type_sub: Optional[Any] = None
        self._view_type_event_sub: Optional[Any] = None

    def start(self) -> None:
        h = self._h
        settings = getattr(h, "_settings", None)
        if not settings:
            return

        # StageCore -> PlayerCore gate
        try:
            self._ready_for_player_sub = settings.subscribe_to_node_change_events(
                getattr(h, "READY_FOR_PLAYER_SETTING", "/younite/player/readyForPlayer"),
                self._on_ready_for_player_changed,
            )
        except Exception:
            self._ready_for_player_sub = None

        # Movement speed multiplier
        try:
            speed_setting = getattr(h, "MOVEMENT_SPEED_SETTING", "/younite/player/movementSpeedMultiplier")
            try:
                cur = settings.get(speed_setting)
                if cur is None:
                    settings.set(speed_setting, 1.0)
            except Exception:
                pass

            self._movement_speed_sub = settings.subscribe_to_node_change_events(
                speed_setting, self._on_movement_speed_changed
            )
            try:
                h.set_movement_speed(float(settings.get(speed_setting) or 1.0))
            except Exception:
                pass
        except Exception:
            self._movement_speed_sub = None

        # Camera view type (bird-eye helper)
        try:
            view_setting = getattr(h, "CAMERA_VIEW_TYPE_SETTING", "/younite/camera/viewType")
            try:
                cur = settings.get(view_setting)
                if cur:
                    h._camera_view_type = str(cur)
            except Exception:
                pass

            def _on_view_type_changed(*_a, **_k):
                try:
                    vt = settings.get(view_setting)
                    if vt:
                        h._camera_view_type = str(vt)
                        # Reset bird-eye mover's locked height when entering bird-eye
                        if h._camera_view_type == "birdEye":
                            mm = getattr(h, "_manual_movement", None)
                            if mm and hasattr(mm, "reset"):
                                mm.reset()
                        # Drop any in-flight bird-eye framer state on view
                        # switch — TeleportService already zeroed the camera's
                        # local rotation, so we just need to forget the saved
                        # original to avoid restoring stale state on the next
                        # bird-eye open.
                        try:
                            framer = getattr(h, "_bird_eye_framer", None)
                            if framer:
                                framer.snap_restore()
                        except Exception:
                            pass
                    # Always drop any session-layer focal length override on
                    # view-type change — first-person and bird-eye share the
                    # same camera prim, so a leftover bird-eye zoom would
                    # silently zoom first-person too. Idempotent when no
                    # override is in flight.
                    try:
                        zoom = getattr(h, "_bird_eye_zoom", None)
                        if zoom:
                            zoom.snap_restore()
                    except Exception:
                        pass
                    # Map rotation (BirdEyeYawService) — same reasoning as
                    # the focal length above: leftover yaw on the camera's
                    # local RotateXYZ.z would silently roll the FP camera
                    # the moment teleport finishes.
                    try:
                        yaw = getattr(h, "_bird_eye_yaw", None)
                        if yaw:
                            yaw.snap_restore()
                    except Exception:
                        pass
                        # Sync PlayerInputController's yaw/pitch with the
                        # camera prim after teleport (TeleportService resets the
                        # camera rotation to (0,0,0) but does not update the
                        # controller's internal state, causing a snap).
                        mc = getattr(h, "_movement_controller", None)
                        if mc and hasattr(mc, "reset_rotation_state"):
                            mc.reset_rotation_state()
                        # Snap player to ground when returning to first-person
                        # (bird's eye spawn point may be at a different height)
                        if h._camera_view_type == "firstPerson":
                            try:
                                import asyncio
                                pb = getattr(h, "_physx_bootstrap", None)
                                pp = getattr(h, "_player_character_path", None) or "/World/PlayerCharacter"
                                if pb:
                                    h._track_task(asyncio.ensure_future(
                                        pb.snap_player_to_ground(pp, frames_wait=5)
                                    ))
                            except Exception:
                                pass
                except Exception:
                    pass

            self._camera_view_type_sub = settings.subscribe_to_node_change_events(view_setting, _on_view_type_changed)
        except Exception:
            self._camera_view_type_sub = None

        # Also observe the eventdispatcher event directly — carb settings
        # callbacks can fire asynchronously, but eventdispatcher observers
        # are invoked synchronously during dispatch.
        try:
            import carb.eventdispatcher
            import carb.events
            import omni.kit.app as kit_app

            evt_name = "younite.camera.viewTypeChanged"
            try:
                kit_app.register_event_alias(carb.events.type_from_string(evt_name), evt_name)
            except Exception:
                pass
            self._view_type_event_sub = carb.eventdispatcher.get_eventdispatcher().observe_event(
                observer_name="younite.player_core/viewTypeChanged",
                event_name=evt_name,
                on_event=lambda evt: _on_view_type_changed(),
                order=0,
            )
        except Exception:
            self._view_type_event_sub = None

        # Catch-up if StageCore already signaled readiness
        try:
            if bool(settings.get(getattr(h, "READY_FOR_PLAYER_SETTING", "/younite/player/readyForPlayer"))):
                h._maybe_init_player()
        except Exception:
            pass

    def stop(self) -> None:
        for sub_name in ("_ready_for_player_sub", "_movement_speed_sub", "_camera_view_type_sub", "_view_type_event_sub"):
            setattr(self, sub_name, None)
        self._h = None

    def _on_movement_speed_changed(self, *_args, **_kwargs) -> None:
        h = self._h
        try:
            settings = getattr(h, "_settings", None)
            if not settings:
                return
            val = settings.get(getattr(h, "MOVEMENT_SPEED_SETTING", "/younite/player/movementSpeedMultiplier"))
            if val is None:
                return
            h.set_movement_speed(float(val))
        except Exception:
            pass

    def _on_ready_for_player_changed(self, *_args, **_kwargs) -> None:
        h = self._h
        try:
            settings = getattr(h, "_settings", None)
            if not settings:
                return
            if bool(settings.get(getattr(h, "READY_FOR_PLAYER_SETTING", "/younite/player/readyForPlayer"))):
                h._maybe_init_player()
            else:
                # readyForPlayer went False (scene switch reset) — clear runtime
                # state so _maybe_init_player can re-run on the new stage.
                # This is the primary reset path; StageEventWiring CLOSED is a
                # secondary safety net (Events 2.0 bridge may not deliver it).
                from ..runtime.player_runtime_state import reset_runtime_state
                reset_runtime_state(h)
        except Exception:
            pass

