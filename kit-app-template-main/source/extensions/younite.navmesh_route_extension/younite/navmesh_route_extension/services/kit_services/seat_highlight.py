"""Runtime seat highlight via PointInstancer prototype swap.

Prototype layout (v3 — 5 prototypes, see ``generate_instancer.py``):
  0 = ChairOrangeUp     (default, upper tier)
  1 = ChairWhiteUp      (default, lower tier)
  2 = ChairOrangeDown   (occupied / nav target — upper tier)
  3 = ChairWhiteDown    (occupied / nav target — lower tier)
  4 = ChairHighlight    (green-glow nav target, Down geometry)

Highlighting publishes a single override at ``HIGHLIGHT_PRIORITY`` via
``seat_proto_override``; that module owns the session-layer
``protoIndices`` opinion and merges in any crowd-driven Down-state
(``seat_fold_state`` runs at the lower ``FOLD_PRIORITY``). The highlight
priority outranks fold-state so the green chair always wins for the
single nav target — including when that seat is also occupied by a
crowd character, which the seated-crowd hide takes care of separately.

This module also drives ``seated_crowd_highlight``: whenever a seat is
highlighted as a navigation target, the seated-crowd character on that
seat is hidden so the green chair is visible. The crowd hide is a
no-op when the seated-crowd payload is missing or when the seat has
no character (e.g. wheelchair/companion tiers, or already hidden by
the current density variant).
"""

from typing import Dict, Optional
import omni.usd

from . import seated_crowd_highlight, seat_proto_override

try:
    from pxr import UsdGeom
except ImportError:
    UsdGeom = None

INSTANCER_PATH = seat_proto_override.INSTANCER_PATH
HIGHLIGHT_INDEX = 4

_seat_index_map: Optional[Dict[str, int]] = None
_highlighted_seat: Optional[str] = None
_highlighted_instance_idx: Optional[int] = None


def _get_stage():
    ctx = omni.usd.get_context()
    return ctx.get_stage() if ctx else None


def _get_instancer():
    """Return the PointInstancer prim, or None."""
    stage = _get_stage()
    if not stage or UsdGeom is None:
        return None
    prim = stage.GetPrimAtPath(INSTANCER_PATH)
    if prim and prim.IsValid():
        return UsdGeom.PointInstancer(prim)
    return None


def _build_seat_index_map() -> Dict[str, int]:
    """Read the seatId primvar and build {seat_number: instance_index}."""
    global _seat_index_map
    instancer = _get_instancer()
    if not instancer:
        _seat_index_map = {}
        return _seat_index_map

    pv_api = UsdGeom.PrimvarsAPI(instancer.GetPrim())
    seat_pv = pv_api.GetPrimvar("seatId")
    if not seat_pv or not seat_pv.HasValue():
        print("[SEAT_HIGHLIGHT] seatId primvar not found on instancer")
        _seat_index_map = {}
        return _seat_index_map

    seat_ids = seat_pv.Get()
    _seat_index_map = {}
    if seat_ids:
        for idx, sid in enumerate(seat_ids):
            _seat_index_map[str(sid)] = idx

    print(f"[SEAT_HIGHLIGHT] Built seat index map: {len(_seat_index_map)} entries")
    return _seat_index_map


def _ensure_map() -> Dict[str, int]:
    global _seat_index_map
    if _seat_index_map is None:
        return _build_seat_index_map()
    return _seat_index_map


def invalidate_cache():
    """Clear the cached seat-to-index mapping (call on variant switch)."""
    global _seat_index_map
    _seat_index_map = None
    seated_crowd_highlight.invalidate_cache()


def highlight_seat(seat_number: str) -> bool:
    """Highlight a single seat by swapping its prototype to the highlight variant.

    Routes through ``seat_proto_override`` so the change composes with
    any crowd-driven Down-state without overwriting it. Automatically
    unhighlights any previously highlighted seat first. Returns True
    on success.
    """
    global _highlighted_seat, _highlighted_instance_idx

    unhighlight_seat()

    seat_map = _ensure_map()
    key = str(seat_number).strip()
    instance_idx = seat_map.get(key)
    if instance_idx is None:
        instance_idx = seat_map.get(key.upper())
        if instance_idx is not None:
            key = key.upper()
    if instance_idx is None:
        print(f"[SEAT_HIGHLIGHT] Seat '{seat_number}' not found in index map")
        return False

    ok = seat_proto_override.set_one(
        instance_idx, HIGHLIGHT_INDEX,
        seat_proto_override.HIGHLIGHT_PRIORITY)
    if not ok:
        return False

    _highlighted_seat = key
    _highlighted_instance_idx = instance_idx
    print(f"[SEAT_HIGHLIGHT] Highlighted seat {seat_number} "
          f"(idx={instance_idx}, proto -> {HIGHLIGHT_INDEX})")

    seated_crowd_highlight.hide_for_seat(key)
    return True


def unhighlight_seat():
    """Remove the highlight; leave the seat in the Down (unfolded) pose.

    Once the user has navigated to a seat, the chair stays unfolded for
    the rest of the session — they have effectively "sat down" there.
    The Down-state is written at ``NAV_VISITED_PRIORITY`` (above
    fold-state, below highlight) so it survives subsequent crowd
    density flips and lets the next nav-target highlight take over
    without losing the previous seat's unfolded state.
    """
    global _highlighted_seat, _highlighted_instance_idx

    if _highlighted_instance_idx is None:
        seated_crowd_highlight.restore()
        return

    idx = _highlighted_instance_idx
    seat_proto_override.clear_one(idx, seat_proto_override.HIGHLIGHT_PRIORITY)
    seat_proto_override.set_down_for_seat(
        idx, seat_proto_override.NAV_VISITED_PRIORITY)

    prev = _highlighted_seat
    _highlighted_seat = None
    _highlighted_instance_idx = None
    print(f"[SEAT_HIGHLIGHT] Unhighlighted seat {prev} "
          f"(left as Down at idx {idx})")

    seated_crowd_highlight.restore()


def get_highlighted_seat() -> Optional[str]:
    """Return the currently highlighted seat number, or None."""
    return _highlighted_seat
