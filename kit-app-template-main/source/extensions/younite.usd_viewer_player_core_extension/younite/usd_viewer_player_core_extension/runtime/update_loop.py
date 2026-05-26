from __future__ import annotations

from typing import Any, Optional

import carb
import carb.eventdispatcher


class PlayerUpdateLoop:
    """Per-frame update loop (movement + small safety repairs)."""

    def __init__(self, host: Any):
        self._h = host
        self._update_subscription: Optional[Any] = None

    def start(self) -> None:
        try:
            import omni.kit.app
            ed = carb.eventdispatcher.get_eventdispatcher()
            self._update_subscription = ed.observe_event(
                observer_name="younite.usd_viewer_player_core_extension/update_loop",
                event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
                on_event=self._on_update,
                order=0,
            )
        except Exception as e:
            print(f"[player_core] Failed to subscribe update loop: {e}")
            self._update_subscription = None

    def stop(self) -> None:
        self._update_subscription = None

    def _on_update(self, event) -> None:
        h = self._h

        try:
            jc = getattr(h, "_jump_controller", None)
            if jc:
                jc.on_update()
        except Exception:
            pass

        try:
            dt = 0.0
            try:
                payload = getattr(event, "payload", None) or {}
                if isinstance(payload, dict):
                    dt = float(payload.get("dt", 0.0))
            except Exception:
                dt = 0.0
            if dt <= 0.0:
                dt = 1.0 / 60.0

            pcm = getattr(h, "_point_click_mover", None)
            # Manual input policy:
            # - Respect navigation state's manual enable/disable.
            # - If a point&click path is running and the user provides manual movement input
            #   (WASD/mobile joystick), manual input cancels the path (interrupt).
            nav = getattr(h, "_nav_orchestrator", None)
            manual_enabled = True
            try:
                if nav and hasattr(nav, "get_manual_input_enabled"):
                    manual_enabled = bool(nav.get_manual_input_enabled())
            except Exception:
                manual_enabled = True

            h._set_manual_input_enabled(manual_enabled)

            mc = getattr(h, "_movement_controller", None)
            if mc:
                mc.update(dt)

            # Bird-eye cinematic tilt animation (panel open / close).
            # Runs after the movement controller so its writes to the camera's
            # local RotateXYZ are not stomped by the same-frame look pipeline.
            # The framer never blocks input — manual drag-pan stays free
            # while the tilt animates, by design.
            try:
                framer = getattr(h, "_bird_eye_framer", None)
                if framer:
                    framer.update(dt)
            except Exception:
                pass

            try:
                yaw_svc = getattr(h, "_bird_eye_yaw", None)
                if yaw_svc and hasattr(yaw_svc, "tick"):
                    yaw_svc.tick(dt)
            except Exception:
                pass

            # If manual movement is active, cancel any running point&click auto-move path.
            try:
                manual_active = bool(getattr(h, "_manual_move_active", False))
                if manual_active and pcm and hasattr(pcm, "is_active") and pcm.is_active():
                    pcm.stop()
            except Exception:
                pass

            # Auto-move step (only when not interrupted by manual movement)
            try:
                manual_active = bool(getattr(h, "_manual_move_active", False))
                if pcm and (not manual_active):
                    pcm.update(dt)
            except Exception:
                pass

            # Player location tracking (diagnostics + reuse by other features)
            try:
                pls = getattr(h, "_player_location_service", None)
                if pls:
                    pls.update(dt)
            except Exception:
                pass
        except Exception:
            pass

        # Viewport camera repair (only if viewport camera is invalid/missing).
        # Skip when a fixed (scene) camera is active so we don't override it.
        try:
            fixed_active = False
            try:
                fixed_active = bool(carb.settings.get_settings().get("/younite/camera/fixedCameraActive"))
            except Exception:
                pass
            if not fixed_active:
                import omni.kit.viewport.utility as vp_utils
                import omni.usd as _omni_usd
                from pxr import UsdGeom
                from younite.usd_viewer_stage_core_extension.services.core_services.world_conventions import (
                    PLAYER_CHARACTER_PATH,
                    player_camera_path,
                )

                cam_path = getattr(h, "_camera_path", None) or (
                    player_camera_path(player_path=getattr(h, "_player_character_path", PLAYER_CHARACTER_PATH))
                )
                vp = vp_utils.get_active_viewport()
                if vp and cam_path:
                    stage = _omni_usd.get_context().get_stage()
                    actual = str(vp.camera_path) if getattr(vp, "camera_path", None) else ""
                    actual_prim = stage.GetPrimAtPath(actual) if (stage and actual) else None
                    actual_valid_camera = bool(actual_prim and actual_prim.IsValid() and actual_prim.IsA(UsdGeom.Camera))
                    if not actual_valid_camera:
                        try:
                            vp.camera_path = cam_path
                        except Exception:
                            pass
        except Exception:
            pass

        # CCT is now managed on-demand via mode_change_callback (no legacy polling needed).

