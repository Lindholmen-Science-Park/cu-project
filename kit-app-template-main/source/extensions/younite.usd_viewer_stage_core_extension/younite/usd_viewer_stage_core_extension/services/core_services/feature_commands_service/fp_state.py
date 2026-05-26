"""
First-person state persistence — capture / store / read / restore the
player's first-person position + rotation across view switches.

Used by ``FeatureCommandsService`` and the directions handlers so the
"return to FP" / "directions back to my previous position" flows can
round-trip without losing where the user was before they entered
bird-eye view.

Persisted in carb settings under ``/younite/player/lastFp*`` so it
survives extension reloads; the position is also mirrored to
``WorldStateSyncService`` for the web overlay.
"""
from __future__ import annotations

from typing import Optional


class FpStateStore:
    """Read/write the player's last first-person transform."""

    def __init__(self, world_state=None):
        self._world_state = world_state

    def capture(self) -> Optional[dict]:
        """Snapshot FP position + body/camera rotation from the live USD stage."""
        try:
            import omni.usd
            from pxr import Usd, UsdGeom

            from ..world_conventions import (
                PLAYER_CHARACTER_PATH,
                PLAYER_FIRST_PERSON_CAMERA_PATH,
            )

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return None
            prim = stage.GetPrimAtPath(PLAYER_CHARACTER_PATH)
            if not prim or not prim.IsValid():
                return None
            cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            m = cache.GetLocalToWorldTransform(prim)
            t = m.ExtractTranslation()
            result = {"x": float(t[0]), "y": float(t[1]), "z": float(t[2])}

            player_xform = UsdGeom.Xformable(prim)
            body_rot_op = (
                player_xform.GetRotateYXZOp() or player_xform.GetRotateXYZOp()
            )
            if body_rot_op:
                br = body_rot_op.Get()
                if br is not None:
                    result["bodyRotX"] = float(br[0])
                    result["bodyRotY"] = float(br[1])
                    result["bodyRotZ"] = float(br[2])

            cam_prim = stage.GetPrimAtPath(PLAYER_FIRST_PERSON_CAMERA_PATH)
            if cam_prim and cam_prim.IsValid():
                cam_xform = UsdGeom.Xformable(cam_prim)
                cam_rot_op = cam_xform.GetRotateXYZOp()
                if cam_rot_op:
                    cr = cam_rot_op.Get()
                    if cr is not None:
                        result["camRotX"] = float(cr[0])
                        result["camRotY"] = float(cr[1])

            return result
        except Exception:
            return None

    def store(self, state: Optional[dict]) -> None:
        """Persist ``state`` (or clear it) to carb settings + world-state sync.

        Pass ``None`` to invalidate (e.g. after the player has returned
        to first person).
        """
        try:
            import carb

            settings = carb.settings.get_settings()
            if state:
                settings.set("/younite/player/lastFpPosX", float(state["x"]))
                settings.set("/younite/player/lastFpPosY", float(state["y"]))
                settings.set("/younite/player/lastFpPosZ", float(state["z"]))
                settings.set("/younite/player/lastFpPosValid", True)
                settings.set(
                    "/younite/player/lastFpBodyRotX",
                    float(state.get("bodyRotX", 0.0)),
                )
                settings.set(
                    "/younite/player/lastFpBodyRotY",
                    float(state.get("bodyRotY", 0.0)),
                )
                settings.set(
                    "/younite/player/lastFpBodyRotZ",
                    float(state.get("bodyRotZ", 0.0)),
                )
                settings.set(
                    "/younite/player/lastFpCamRotX",
                    float(state.get("camRotX", 0.0)),
                )
                settings.set(
                    "/younite/player/lastFpCamRotY",
                    float(state.get("camRotY", 0.0)),
                )
            else:
                settings.set("/younite/player/lastFpPosValid", False)
        except Exception:
            pass
        if self._world_state:
            ws_pos = (
                {"x": state["x"], "y": state["y"], "z": state["z"]}
                if state
                else None
            )
            self._world_state.set("lastFirstPersonPosition", ws_pos)

    def read(self) -> Optional[dict]:
        """Return the stored FP state, or ``None`` if nothing is valid."""
        try:
            import carb

            settings = carb.settings.get_settings()
            if settings.get("/younite/player/lastFpPosValid"):
                return {
                    "pos": (
                        float(settings.get("/younite/player/lastFpPosX") or 0),
                        float(settings.get("/younite/player/lastFpPosY") or 0),
                        float(settings.get("/younite/player/lastFpPosZ") or 0),
                    ),
                    "bodyRotX": float(
                        settings.get("/younite/player/lastFpBodyRotX") or 0
                    ),
                    "bodyRotY": float(
                        settings.get("/younite/player/lastFpBodyRotY") or 0
                    ),
                    "bodyRotZ": float(
                        settings.get("/younite/player/lastFpBodyRotZ") or 0
                    ),
                    "camRotX": float(
                        settings.get("/younite/player/lastFpCamRotX") or 0
                    ),
                    "camRotY": float(
                        settings.get("/younite/player/lastFpCamRotY") or 0
                    ),
                }
        except Exception:
            pass
        return None

    def restore_rotation(self, stored: dict) -> None:
        """Write stored body + camera rotation to USD and sync the input controller.

        Dispatches ``younite.player.immediateViewAngles`` so
        ``PlayerInputController`` re-syncs its cached yaw/pitch to the
        values we just authored. Without that sync the next mouse /
        touch delta would write ``cached_yaw + dx`` and snap the view
        away from the restored rotation.
        """
        try:
            import omni.usd
            from pxr import Gf, UsdGeom

            from ..world_conventions import (
                PLAYER_CHARACTER_PATH,
                PLAYER_FIRST_PERSON_CAMERA_PATH,
            )

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            body_rot_x = float(stored.get("bodyRotX", 0.0))
            body_rot_y = float(stored.get("bodyRotY", 0.0))
            body_rot_z = float(stored.get("bodyRotZ", 0.0))
            cam_rot_x = float(stored.get("camRotX", 0.0))
            cam_rot_y = float(stored.get("camRotY", 0.0))

            player_prim = stage.GetPrimAtPath(PLAYER_CHARACTER_PATH)
            if player_prim and player_prim.IsValid():
                px = UsdGeom.Xformable(player_prim)
                rot_op = px.GetRotateYXZOp() or px.GetRotateXYZOp()
                if rot_op:
                    rot_op.Set(Gf.Vec3d(body_rot_x, body_rot_y, body_rot_z))

            cam_prim = stage.GetPrimAtPath(PLAYER_FIRST_PERSON_CAMERA_PATH)
            if cam_prim and cam_prim.IsValid():
                cx = UsdGeom.Xformable(cam_prim)
                cam_rot = cx.GetRotateXYZOp() or cx.AddRotateXYZOp()
                cam_rot.Set(Gf.Vec3d(cam_rot_x, cam_rot_y, 0.0))

            try:
                from younite.messaging_core_extension.message_utils import (
                    dispatch_to_events2,
                )

                dispatch_to_events2(
                    "younite.player.immediateViewAngles",
                    {"yaw": cam_rot_y, "pitch": cam_rot_x},
                )
            except Exception:
                pass
        except Exception:
            pass


__all__ = ["FpStateStore"]
