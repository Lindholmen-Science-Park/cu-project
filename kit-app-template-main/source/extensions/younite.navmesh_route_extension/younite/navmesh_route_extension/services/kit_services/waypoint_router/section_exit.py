"""Map seat section letters to corridor ring exit indices."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .config import UPPER_SECTION_BRANCH
from .ring_navmesh import nearest_index


def exit_index_for_section(
    ring: List[Tuple[str, Tuple[float, float, float]]],
    section: str,
    all_wps: Dict[str, Tuple[float, float, float]],
) -> Optional[int]:
    """
    Find the ring index to exit at for ``section``.

    For upper-level sections, finds the nearest ring waypoint to the
    staircase access point (which is off-ring).  For main corridor sections,
    finds ``nav_waypoint_{section}`` directly on the ring.
    """
    upper = section.upper()

    if upper in UPPER_SECTION_BRANCH:
        staircase_name = UPPER_SECTION_BRANCH[upper][0]
        staircase_pos = all_wps.get(staircase_name)
        if not staircase_pos:
            print(f"[waypoint_router] Staircase waypoint '{staircase_name}' not found on stage")
            return None
        idx = nearest_index(ring, staircase_pos)
        print(
            f"[waypoint_router] Section '{section}' -> staircase '{staircase_name}' "
            f"-> nearest ring '{ring[idx][0]}' (index {idx})"
        )
        return idx

    target_name = f"nav_waypoint_{upper}"
    for i, (name, _) in enumerate(ring):
        if name == target_name:
            print(f"[waypoint_router] Section '{section}' -> ring exit '{target_name}' (index {i})")
            return i

    print(f"[waypoint_router] No waypoint found for section '{section}' (looked for '{target_name}')")
    return None
