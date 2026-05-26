"""
Predicate-driven readiness for camera / view transitions.

Waits until the stadium LOD (published by lod_management_extension via
carb setting ``/younite/stadium/currentLod``) matches the requested view
type, polling once per Kit update.  A monotonic deadline caps total wait
(safety only); there is no fixed "success path" frame count.

Teleport correctness is *not* verified here — ``move_player_to_spawnpoint``
is synchronous and its return value already indicates success/failure.
"""

from __future__ import annotations

import time
from typing import Optional

_LOD_SETTING = "/younite/stadium/currentLod"


def _expected_stadium_lod_for_view_type(view_type: str) -> Optional[str]:
    if view_type == "birdEye":
        return "light"
    if view_type == "firstPerson":
        return "full"
    return None


def _read_stadium_lod() -> Optional[str]:
    try:
        import carb
        val = carb.settings.get_settings().get(_LOD_SETTING)
        return str(val).strip() if val else None
    except Exception:
        return None


async def await_stadium_lod_for_view_type(view_type: str, *, deadline: float) -> bool:
    """True if LOD matches (or setting absent — nothing to wait on). False if deadline passed."""
    import omni.kit.app as kit_app

    expected = _expected_stadium_lod_for_view_type(view_type)
    if expected is None:
        return True

    while time.monotonic() < deadline:
        cur = _read_stadium_lod()
        if cur is None:
            return True
        if cur == expected:
            return True
        await kit_app.get_app().next_update_async()
    return False


async def await_view_transition_scene_ready(
    view_type: str,
    *,
    deadline: float,
) -> None:
    """
    Wait until the stadium LOD matches *view_type*.
    Logs on timeout; callers still dispatch viewTransitionReady so the UI never sticks.
    """
    expected = _expected_stadium_lod_for_view_type(view_type)

    if expected is not None:
        lod_ok = await await_stadium_lod_for_view_type(view_type, deadline=deadline)
        if not lod_ok:
            print(
                f"[view_transition_readiness] deadline waiting for stadium LOD "
                f"(want {expected!r} for {view_type})"
            )
