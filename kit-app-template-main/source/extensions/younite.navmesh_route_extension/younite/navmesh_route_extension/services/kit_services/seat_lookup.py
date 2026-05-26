"""Seat position lookup: maps seat ID -> world coordinates.

Loads ``seats_lookup.json`` (compact: ``{"A-4-15":[x,y,z], ...}``), produced by
``data/Assets/Seats/Tools/create_lookup.py``. Regenerate after USD seat-group
transform changes or after changing ``seat_pivot_offset.py`` (lookup XY matches
PointInstancer instance origins).

Variant config is stored in seating_variants.json:
    {"all_seats": null, "half_capacity": "availability_half_capacity.json"}

When a variant is selected, the matching availability file is loaded
to filter which seats are navigable.
"""

import json
import os
from typing import List, Optional, Tuple, Dict, Set

_lookup: Optional[Dict[str, list]] = None
_available: Optional[Set[str]] = None
_active_variant: Optional[str] = None
_variant_config: Optional[Dict[str, Optional[str]]] = None
_bbox_center_xz: Optional[Tuple[float, float]] = None

_CONFIG_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "config"))


def _load_json(filename: str) -> Optional[dict]:
    p = os.path.join(_CONFIG_DIR, filename)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[SEAT_LOOKUP] Failed to load {p}: {e}")
        return None


def _load_variant_config() -> Dict[str, Optional[str]]:
    global _variant_config
    if _variant_config is not None:
        return _variant_config

    data = _load_json("seating_variants.json")
    if data and isinstance(data, dict):
        _variant_config = data
        print(f"[SEAT_LOOKUP] Variant config loaded: {list(_variant_config.keys())}")
    else:
        _variant_config = {}

    return _variant_config


def _load_availability_for_variant(variant_name: Optional[str]) -> Optional[Set[str]]:
    """Load the availability set for a given variant name."""
    config = _load_variant_config()

    if config:
        # If variant config exists, resolve the effective variant name.
        # On startup (variant_name is None), default to the first variant
        # so we stay in sync with the USD file's default variant selection.
        effective = variant_name if variant_name in config else next(iter(config), None)
        if effective is not None:
            avail_filename = config.get(effective)
            if avail_filename is None:
                return None
            avail_data = _load_json(avail_filename)
            if avail_data and "available_seats" in avail_data:
                return set(avail_data["available_seats"])
            return None

    # Legacy fallback: no variant config at all
    avail_data = _load_json("availability.json")
    if avail_data and "available_seats" in avail_data:
        return set(avail_data["available_seats"])
    return None


def _ensure_loaded() -> Dict[str, list]:
    global _lookup, _available
    if _lookup is not None:
        return _lookup

    data = _load_json("seats_lookup.json")
    if data is None:
        print("[SEAT_LOOKUP] seats_lookup.json not found in config")
        _lookup = {}
    else:
        _lookup = data
        print(f"[SEAT_LOOKUP] Loaded {len(_lookup)} seats")

    _available = _load_availability_for_variant(_active_variant)
    if _available is not None:
        variant_label = _active_variant or "default"
        print(f"[SEAT_LOOKUP] Availability for '{variant_label}': {len(_available)} seats")
    else:
        print("[SEAT_LOOKUP] No availability filter (all seats available)")

    return _lookup


def _normalize_seat_number(seat_number: str) -> Optional[str]:
    """Resolve a seat ID to the key used in the lookup dict.

    Accepts IDs like "A-4-15" directly.  Also tries upper-casing for
    case-insensitive matching.
    """
    lookup = _ensure_loaded()
    key = seat_number.strip()
    if key in lookup:
        return key
    upper = key.upper()
    if upper in lookup:
        return upper
    return None


def is_seat_available(seat_number: str) -> Optional[bool]:
    """Check if a seat is available. Returns None if seat doesn't exist."""
    key = _normalize_seat_number(seat_number)
    if key is None:
        return None
    if _available is None:
        return True
    return key in _available


def get_seat_position(seat_number: str) -> Optional[Tuple[float, float, float]]:
    """Look up a seat by number string. Returns (x, y, z) world position or None."""
    key = _normalize_seat_number(seat_number)
    if key is None:
        return None

    pos = _ensure_loaded().get(key)
    if pos and len(pos) >= 3:
        return (float(pos[0]), float(pos[1]), float(pos[2]))
    return None


def camera_local_yaw_to_face_world_xz(
    player_prim,
    observer_x: float,
    observer_z: float,
    target_x: float,
    target_z: float,
) -> Optional[float]:
    """Camera-local yaw (deg) for first_person_camera RotateXYZ so view faces target XZ from observer.

    Matches NavigationOrchestratorService.face_toward_world_xz convention (world yaw from atan2, minus player root yaw).
    """
    import math

    try:
        from pxr import UsdGeom
    except Exception:
        return None

    dx = float(target_x) - float(observer_x)
    dz = float(target_z) - float(observer_z)
    if dx * dx + dz * dz < 1e-12:
        return None

    world_yaw = math.degrees(math.atan2(-dx, -dz))

    parent_yaw = 0.0
    try:
        p_xf = UsdGeom.Xformable(player_prim)
        rot_op = p_xf.GetRotateXYZOp()
        if rot_op and rot_op.Get():
            parent_yaw = float(rot_op.Get()[1])
        else:
            rot_op = p_xf.GetRotateYXZOp()
            if rot_op and rot_op.Get():
                parent_yaw = float(rot_op.Get()[0])
    except Exception:
        pass

    return float(world_yaw - parent_yaw)


def get_seat_positions_bbox_center_xz() -> Optional[Tuple[float, float]]:
    """Axis-aligned bbox center of all seat positions in XZ (bowl / stadium plan center)."""
    global _bbox_center_xz
    if _bbox_center_xz is not None:
        return _bbox_center_xz
    lookup = _ensure_loaded()
    xs: List[float] = []
    zs: List[float] = []
    for pos in lookup.values():
        if isinstance(pos, (list, tuple)) and len(pos) >= 3:
            xs.append(float(pos[0]))
            zs.append(float(pos[2]))
    if not xs:
        return None
    _bbox_center_xz = ((min(xs) + max(xs)) * 0.5, (min(zs) + max(zs)) * 0.5)
    return _bbox_center_xz


def set_active_variant(variant_name: str):
    """Switch to a different seating variant. Reloads availability data."""
    global _active_variant, _available
    _active_variant = variant_name
    _available = _load_availability_for_variant(variant_name)
    if _available is not None:
        print(f"[SEAT_LOOKUP] Switched to variant '{variant_name}': {len(_available)} seats available")
    else:
        print(f"[SEAT_LOOKUP] Switched to variant '{variant_name}': all seats available")


def get_active_variant() -> Optional[str]:
    """Return the currently active variant name."""
    return _active_variant


def get_available_variants() -> Optional[Dict[str, Optional[str]]]:
    """Return the variant config dict, or None if no variants configured."""
    config = _load_variant_config()
    return config if config else None


def reload():
    """Force reload of the lookup, availability, and variant config."""
    global _lookup, _available, _variant_config, _bbox_center_xz
    _lookup = None
    _available = None
    _variant_config = None
    _bbox_center_xz = None


def get_seat_count() -> int:
    """Return total number of seats in the lookup."""
    return len(_ensure_loaded())


def get_available_count() -> int:
    """Return number of available seats (all if no availability filter)."""
    _ensure_loaded()
    if _available is None:
        return len(_lookup or {})
    return len(_available)
