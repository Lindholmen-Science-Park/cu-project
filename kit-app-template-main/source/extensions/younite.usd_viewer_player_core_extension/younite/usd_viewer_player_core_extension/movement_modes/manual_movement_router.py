from __future__ import annotations

from typing import Any, Dict, Optional

from .bird_eye_usd_translate_mover import BirdEyeUsdTranslateMover
from .first_person_cct_mover import FirstPersonCctMover
from younite.usd_viewer_stage_core_extension.services.core_services.world_conventions import PLAYER_CHARACTER_PATH


class ManualMovementRouter:
    """
    Chooses which *movement implementation* to use for manual input:

    - `birdEye` view: USD-translate mover (locked height)
    - otherwise: PhysX CCT control_state.inputs mover

    This intentionally contains the "routing" logic that used to be hidden in
    `CctLocalInputMover`, so the codebase reflects reality.
    """

    def __init__(self, host: Any):
        self._h = host
        self._bird_eye = BirdEyeUsdTranslateMover()

    def reset(self) -> None:
        self._bird_eye.reset()

    def drive(self, dt: float, movement_state: Dict[str, Any]) -> None:
        h = self._h

        # Determine view type (birdEye vs firstPerson)
        view_type = getattr(h, "_camera_view_type", "firstPerson") or "firstPerson"
        if view_type == "firstPerson" and hasattr(h, "_camera_service") and h._camera_service:
            try:
                view_type = getattr(h._camera_service, "_current_view_type", "firstPerson") or "firstPerson"
            except Exception:
                view_type = "firstPerson"

        if str(view_type) == "birdEye":
            try:
                import omni.usd as _omni_usd

                stage = _omni_usd.get_context().get_stage()
            except Exception:
                stage = None

            # Prefer yaw from movement controller (so p&c / mouselook still affects bird-eye heading)
            fallback_yaw = 0.0
            try:
                mc = getattr(h, "_movement_controller", None)
                if mc is not None and hasattr(mc, "get_view_angles"):
                    fallback_yaw = float(mc.get_view_angles()[0])
            except Exception:
                pass

            handled = self._bird_eye.drive(
                stage=stage,
                player_path=str(getattr(h, "_player_character_path", PLAYER_CHARACTER_PATH)),
                camera_path=getattr(h, "_camera_path", None),
                movement_state=movement_state,
                dt=float(dt),
                speed_multiplier=float(getattr(h, "_movement_speed_multiplier", 1.0)),
                fallback_yaw_deg=float(fallback_yaw),
            )
            if handled:
                return

        # First-person: PhysX CharacterController control_state.inputs
        cc = getattr(h, "_nv_character_controller", None)
        if not cc:
            return
        try:
            FirstPersonCctMover(character_controller=cc).drive(movement_state)
        except Exception:
            pass

