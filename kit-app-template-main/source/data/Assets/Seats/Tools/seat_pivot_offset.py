"""Seat mesh pivot vs CAD label — **visual-only** XY correction (mm, Z-up).

``extracted_seats_with_rows.json`` (and event JSON) stay **raw CAD** coordinates.
``create_lookup.py`` applies the same XY pivot as the instancer so navigation
matches instance origins (Z still from JSON).

Apply ``visual_seat_xy_mm()`` when building PointInstancer positions for chairs
and seated people so rendered assets align with the bowl.

**Negative** mm on upper/companion moves toward the tier riser; **positive** mm
on white TELE moves the opposite way (forward in plan). Flip constants if CAD
rotation convention changes.

Per tier (see ``pivot_offset_mm_for_tier``):

* ``upper``: −300 mm (toward riser)
* ``companion``: −250 mm (toward riser, but 50 mm less than upper). The
  ArenaSeatV2 model has a backrest that curves rearwards; companion
  seats sit against a wall, so this 5 cm forward bias keeps the
  curved back from clipping into it. Upper-tier seats are unaffected.
* ``lower``, ``lower2``, ``extra_lower`` (white TELE): +60 mm (forward vs that)
* ``wheelchair``, ``parkett``: no XY pivot
"""

from __future__ import annotations

import math

SEAT_PIVOT_UPPER_MM = -300.0
SEAT_PIVOT_COMPANION_MM = -250.0
# Opposite sign from upper: nudges white TELE instances forward in plan (mm).
SEAT_PIVOT_TELE_LOWER_MM = 60.0

TELE_LOWER_TIERS = frozenset({"lower", "lower2", "extra_lower"})

# Back-compat alias used by callers that derive a generic "back offset"
# from the upper pivot (e.g. seated-crowd backrest alignment).
SEAT_PIVOT_UPPER_COMPANION_MM = SEAT_PIVOT_UPPER_MM
SEAT_PIVOT_BACK_OFFSET_MM = SEAT_PIVOT_UPPER_MM


def pivot_offset_mm_for_tier(tier: str | None) -> float | None:
    """Return delta mm for ``R_z @ (0, -off)``, or None if this tier is not shifted."""
    if tier == "upper":
        return SEAT_PIVOT_UPPER_MM
    if tier == "companion":
        return SEAT_PIVOT_COMPANION_MM
    if tier in TELE_LOWER_TIERS:
        return SEAT_PIVOT_TELE_LOWER_MM
    return None


def seat_receives_pivot_offset(seat: dict) -> bool:
    """True if instancer generation applies a non-zero XY pivot for this seat."""
    return pivot_offset_mm_for_tier(seat.get("tier")) is not None


def pivot_offset_dxy(rotation_deg: float, offset_mm: float | None = None) -> tuple[float, float]:
    off = SEAT_PIVOT_UPPER_COMPANION_MM if offset_mm is None else offset_mm
    rad = math.radians(float(rotation_deg))
    dx = off * math.sin(rad)
    dy = -off * math.cos(rad)
    return dx, dy


def visual_seat_xy_mm(seat: dict) -> tuple[float, float]:
    """Instancer-local XY (mm): CAD ``x,y`` plus tier mesh pivot correction."""
    x = float(seat["x"])
    y = float(seat["y"])
    off = pivot_offset_mm_for_tier(seat.get("tier"))
    if off is None or "rotation" not in seat:
        return x, y
    dx, dy = pivot_offset_dxy(float(seat["rotation"]), off)
    return (x + dx, y + dy)


def strip_visual_pivot_from_seat_json_records(seats: list) -> int:
    """One-time migration: remove baked pivot from JSON (restore raw CAD).

    For each tier that uses a visual offset, replace stored ``x,y`` with
    ``P - f(off)`` so data matches DXF again. **Do not run** on JSON that is
    already CAD-true.
    """
    n = 0
    for s in seats:
        off = pivot_offset_mm_for_tier(s.get("tier"))
        if off is None:
            continue
        if "rotation" not in s or "x" not in s or "y" not in s:
            continue
        dx, dy = pivot_offset_dxy(float(s["rotation"]), -off)
        s["x"] = round(float(s["x"]) + dx, 2)
        s["y"] = round(float(s["y"]) + dy, 2)
        n += 1
    return n
