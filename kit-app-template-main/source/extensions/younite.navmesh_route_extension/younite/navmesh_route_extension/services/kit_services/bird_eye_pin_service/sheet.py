"""Outbound ``birdEyePinSheet`` / ``birdEyePinError`` dispatches."""

from __future__ import annotations

from typing import Any, Dict, Tuple


def dispatch_pin_sheet(
    *,
    world: Tuple[float, float, float],
    title: str,
    spawn_point: str,
    magnet_name: str,
    is_inside: bool,
) -> None:
    try:
        from younite.messaging_core_extension.message_utils import dispatch_to_events2

        payload: Dict[str, Any] = {
            "id": f"pin_{int(world[0])}_{int(world[2])}",
            "title": title,
            "spawnPoint": spawn_point,
            "magnetName": magnet_name,
            "isInsideNavmesh": bool(is_inside),
            "worldPos": {"x": float(world[0]), "y": float(world[1]), "z": float(world[2])},
        }
        dispatch_to_events2("birdEyePinSheet", payload)
    except Exception as e:
        print(f"[bird_eye_pin] dispatch sheet failed: {e}")


def dispatch_pin_error(message: str) -> None:
    try:
        from younite.messaging_core_extension.message_utils import dispatch_to_events2

        dispatch_to_events2("birdEyePinError", {"error": message})
    except Exception:
        pass
