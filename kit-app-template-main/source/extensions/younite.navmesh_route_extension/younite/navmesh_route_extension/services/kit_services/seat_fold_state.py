"""Crowd-driven seat fold state — occupied seats are Down, empty seats are Up.

The seated-crowd PointInstancer carries a ``primvars:seatId`` that
mirrors the seat instancer's ``primvars:seatId``. Combined with the
active ``crowd_density`` variant's ``invisibleIds`` (per-character
visibility mask) we can derive, in O(N), the set of seat ids whose
character is *visible* — i.e. seats that are "occupied".

For every occupied seat we push a Down-state override to
``seat_proto_override`` (priority ``FOLD_PRIORITY``). Empty seats fall
back to the variant's authored Up-state. The seat-nav highlight (and
its higher priority) wins over the Down-state for the single nav
target, so the highlighted seat keeps its green-glow Down look.

This module is a no-op (silent) when:

* The seated crowd payload is not yet loaded (early startup).
* The seat instancer is not loaded yet.
* The seated-crowd density is ``none`` (no characters → no occupied
  seats → empty override map).
* ``pxr`` cannot be imported.

Trigger points (wired in ``extension.py``):

* ``seatedCrowdLayoutChanged`` — variant flip from web/dev UI.
* Initial pass after the seated-crowd payload becomes available
  (debounced ``stage_event:OPENED`` / ``ASSETS_LOADED``).
"""

from typing import Dict, List, Optional, Set, Tuple
import omni.usd

from . import seat_proto_override

try:
    from pxr import Usd, UsdGeom
except ImportError:
    Usd = None
    UsdGeom = None

CROWD_INSTANCER_PATH = "/World/Skandinavium/seated_people/PeopleInstancer"

# Mirrors prototype indices in generate_instancer.py.
PROTO_ORANGE_UP = 0
PROTO_WHITE_UP = 1
PROTO_ORANGE_DOWN = 2
PROTO_WHITE_DOWN = 3

_UP_TO_DOWN = {
    PROTO_ORANGE_UP: PROTO_ORANGE_DOWN,
    PROTO_WHITE_UP: PROTO_WHITE_DOWN,
}


def _get_stage():
    ctx = omni.usd.get_context()
    return ctx.get_stage() if ctx else None


def _get_crowd_instancer():
    stage = _get_stage()
    if not stage or UsdGeom is None:
        return None
    prim = stage.GetPrimAtPath(CROWD_INSTANCER_PATH)
    if prim and prim.IsValid():
        return UsdGeom.PointInstancer(prim)
    return None


def _get_seat_instancer():
    stage = _get_stage()
    if not stage or UsdGeom is None:
        return None
    prim = stage.GetPrimAtPath(seat_proto_override.INSTANCER_PATH)
    if prim and prim.IsValid():
        return UsdGeom.PointInstancer(prim)
    return None


def _strongest_crowd_invisible_ids() -> List[int]:
    """Read ``invisibleIds`` from the strongest opinion (variant-applied
    or session-layer override). The crowd's ``crowd_density`` VariantSet
    writes into the layer beneath the session, so this picks up the
    active density's hidden-character set."""
    instancer = _get_crowd_instancer()
    if instancer is None or Usd is None:
        return []
    val = instancer.GetInvisibleIdsAttr().Get()
    if val is None:
        return []
    return [int(x) for x in val]


def _build_seat_index_map() -> Dict[str, int]:
    """``seat_id -> instance index`` for the seat instancer."""
    inst = _get_seat_instancer()
    if inst is None:
        return {}
    pv_api = UsdGeom.PrimvarsAPI(inst.GetPrim())
    seat_pv = pv_api.GetPrimvar("seatId")
    if not seat_pv or not seat_pv.HasValue():
        return {}
    return {str(sid): idx for idx, sid in enumerate(seat_pv.Get() or [])}


def _build_seat_proto_baseline() -> List[int]:
    """Baseline (variant) protoIndices from the seat instancer."""
    inst = _get_seat_instancer()
    if inst is None:
        return []
    base = seat_proto_override._baseline_proto_indices()  # noqa: SLF001
    if base is not None:
        return base
    val = inst.GetProtoIndicesAttr().Get()
    return list(int(x) for x in (val or []))


def _occupied_seat_ids() -> Optional[Set[str]]:
    """Set of seat ids that currently have a *visible* crowd character.

    Returns ``None`` when the crowd is not loaded (caller should not
    push any override in that case — the seats stay Up). Returns an
    empty set when the crowd is loaded but no character is visible
    (density = none). The latter is meaningful: the override map
    should be cleared so any prior Down-state goes away.
    """
    crowd = _get_crowd_instancer()
    if crowd is None:
        return None

    pv_api = UsdGeom.PrimvarsAPI(crowd.GetPrim())
    seat_pv = pv_api.GetPrimvar("seatId")
    if not seat_pv or not seat_pv.HasValue():
        return None
    seat_ids = list(seat_pv.Get() or [])

    inst_ids = crowd.GetIdsAttr().Get()
    invisible = set(_strongest_crowd_invisible_ids())
    if not seat_ids:
        return set()

    occupied: Set[str] = set()
    for i, sid in enumerate(seat_ids):
        crowd_id = int(inst_ids[i]) if inst_ids is not None and i < len(inst_ids) else int(i)
        if crowd_id not in invisible:
            occupied.add(str(sid))
    return occupied


def _compute_overrides() -> Tuple[Optional[Dict[int, Tuple[int, int]]], int]:
    """Build the ``{seat_idx: (proto, priority)}`` map for occupied seats.

    Returns ``(None, 0)`` when the crowd payload is missing — the caller
    should leave existing overrides alone in that case (early startup).
    """
    occupied = _occupied_seat_ids()
    if occupied is None:
        return None, 0

    seat_map = _build_seat_index_map()
    if not seat_map:
        return {}, 0

    baseline = _build_seat_proto_baseline()
    if not baseline:
        return {}, 0

    overrides: Dict[int, Tuple[int, int]] = {}
    for sid in occupied:
        idx = seat_map.get(sid)
        if idx is None or idx >= len(baseline):
            continue
        down = _UP_TO_DOWN.get(int(baseline[idx]))
        if down is None:
            continue
        overrides[idx] = (down, seat_proto_override.FOLD_PRIORITY)
    return overrides, len(occupied)


def refresh() -> bool:
    """Recompute occupied → Down overrides and flush via seat_proto_override.

    Idempotent — safe to call repeatedly. Silent no-op if crowd not
    loaded.
    """
    overrides, occ_count = _compute_overrides()
    if overrides is None:
        # Crowd payload not loaded yet — defer.
        return False
    seat_proto_override.set_overrides(
        overrides, clear_priority=seat_proto_override.FOLD_PRIORITY)
    print(f"[SEAT_FOLD] Applied Down-state to {len(overrides)} occupied "
          f"seats ({occ_count} crowd characters visible)")
    return True


def reset():
    """Drop all fold-state overrides (e.g. on stage close)."""
    seat_proto_override.set_overrides(
        {}, clear_priority=seat_proto_override.FOLD_PRIORITY)
