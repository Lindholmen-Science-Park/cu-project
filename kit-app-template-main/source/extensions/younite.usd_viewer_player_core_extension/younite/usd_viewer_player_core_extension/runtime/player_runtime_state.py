from __future__ import annotations

from typing import Any


def reset_runtime_state(host: Any) -> None:
    """Reset runtime state so player can be re-initialized after scene switch."""
    try:
        # Mark settings-backed readiness false
        try:
            settings = getattr(host, "_settings", None)
            if settings:
                settings.set(getattr(host, "PLAYER_READY_SETTING", "/younite/player/ready"), False)
        except Exception:
            pass

        # Player/CCT
        host._player_character_path = None
        host._camera_path = None
        host._nv_cct_interface = None
        host._nv_character_controller = None
        host._physx_initialized = False
        host._player_initialized = False
        host._nvidia_controls_active = False
        host._nvidia_input_bound = False

        try:
            from younite.usd_viewer_stage_core_extension.services.core_services.world_conventions import get_default_view_type
            host._camera_view_type = get_default_view_type()
        except Exception:
            host._camera_view_type = "firstPerson"
        try:
            mm = getattr(host, "_manual_movement", None)
            if mm and hasattr(mm, "reset"):
                mm.reset()
        except Exception:
            pass
        try:
            mc = getattr(host, "_movement_controller", None)
            if mc:
                mc.reset_rotation_state()
        except Exception:
            pass

        # Jump reset flags
        try:
            host._reset_jump_next_frame = False
            host._jump_control_state = None
        except Exception:
            pass
    except Exception as e:
        print(f"[player_core] reset runtime state failed: {e}")

