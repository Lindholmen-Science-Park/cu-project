"""Hide a single seated-crowd character while its seat is highlighted as
a navigation target.

Companion to ``seat_highlight.py`` — that module swaps the seat's
prototype to the green ``ChairHighlight``; this module additionally
adds the *character* sitting on that seat to the seated-crowd
PointInstancer's ``invisibleIds`` so the user can actually see the
glowing target chair through what would otherwise be a silhouette.

Mechanism (mirrors ``seat_highlight``):
  * Maps ``seatId -> instance id`` by reading the ``primvars:seatId``
    + ``ids`` arrays on
    ``/World/Skandinavium/seated_people/PeopleInstancer``.
  * Writes a unioned ``invisibleIds`` value to the **session layer**
    only — the variant's authored ``invisibleIds`` (which encodes the
    crowd-density variant) is never modified.
  * Reads the variant baseline by walking the property stack and
    skipping the session-layer opinion (so we always union against the
    correct density), making the override stable across density flips
    when ``on_variant_changed()`` is called.

The module is a no-op (returns ``False`` / does nothing) when the
seated-crowd payload has not loaded yet, when the seat ID is unknown,
or when ``pxr`` cannot be imported. Callers can call without guards.
"""

from typing import Dict, List, Optional

import omni.usd

try:
    from pxr import Sdf, Usd, UsdGeom, Vt
except ImportError:
    Sdf = None
    Usd = None
    UsdGeom = None
    Vt = None

INSTANCER_PATH = "/World/Skandinavium/seated_people/PeopleInstancer"

_seat_to_crowd_id: Optional[Dict[str, int]] = None
_currently_hidden_seat: Optional[str] = None


def _get_stage():
    ctx = omni.usd.get_context()
    return ctx.get_stage() if ctx else None


def _get_instancer():
    stage = _get_stage()
    if not stage or UsdGeom is None:
        return None
    prim = stage.GetPrimAtPath(INSTANCER_PATH)
    if prim and prim.IsValid():
        return UsdGeom.PointInstancer(prim)
    return None


def _build_seat_id_map() -> Dict[str, int]:
    """Read ``primvars:seatId`` + ``ids`` and build ``{seat_id: crowd_id}``."""
    global _seat_to_crowd_id
    instancer = _get_instancer()
    if instancer is None:
        _seat_to_crowd_id = {}
        return _seat_to_crowd_id

    pv_api = UsdGeom.PrimvarsAPI(instancer.GetPrim())
    seat_pv = pv_api.GetPrimvar("seatId")
    if not seat_pv or not seat_pv.HasValue():
        print("[SEATED_CROWD_HL] seatId primvar not found on instancer "
              "(regenerate seated_people.usda)")
        _seat_to_crowd_id = {}
        return _seat_to_crowd_id

    seat_ids = seat_pv.Get() or []
    inst_ids = instancer.GetIdsAttr().Get()  # may be None -> use index

    mapping: Dict[str, int] = {}
    for i, sid in enumerate(seat_ids):
        crowd_id = int(inst_ids[i]) if inst_ids is not None and i < len(inst_ids) else int(i)
        mapping[str(sid)] = crowd_id
    _seat_to_crowd_id = mapping
    print(f"[SEATED_CROWD_HL] Built seatId -> crowd id map: "
          f"{len(mapping)} entries")
    return mapping


def _ensure_map() -> Dict[str, int]:
    if _seat_to_crowd_id is None:
        return _build_seat_id_map()
    return _seat_to_crowd_id


def invalidate_cache():
    """Drop the cached ``seat_id -> crowd_id`` mapping.

    Call after the seated-crowd payload reloads or after the
    PointInstancer's instance arrays change (which currently never
    happens at runtime — variants only modify ``invisibleIds`` — but
    this is symmetric with ``seat_highlight.invalidate_cache``).
    """
    global _seat_to_crowd_id
    _seat_to_crowd_id = None


def _baseline_invisible_ids() -> List[int]:
    """Return ``invisibleIds`` from the strongest *non-session* opinion.

    Walking the property stack lets us see the variant's authored value
    even when our own session-layer override is in place.
    """
    instancer = _get_instancer()
    if instancer is None:
        return []
    stage = _get_stage()
    session = stage.GetSessionLayer()
    attr = instancer.GetInvisibleIdsAttr()
    for spec in attr.GetPropertyStack(Usd.TimeCode.Default()):
        if spec.layer == session:
            continue
        default = spec.default
        if default is not None:
            return [int(x) for x in default]
    return []


def _set_session_invisible_ids(ids: List[int]):
    instancer = _get_instancer()
    if instancer is None:
        return
    stage = _get_stage()
    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, session):
        instancer.GetInvisibleIdsAttr().Set(Vt.Int64Array(ids))


def _clear_session_invisible_ids():
    instancer = _get_instancer()
    if instancer is None:
        return
    stage = _get_stage()
    session = stage.GetSessionLayer()
    attr = instancer.GetInvisibleIdsAttr()
    with Usd.EditContext(stage, session):
        attr.Clear()


def hide_for_seat(seat_id: str) -> bool:
    """Hide the crowd character that sits on ``seat_id``.

    Tracks the hidden seat so a subsequent variant flip can re-apply the
    override against the new density baseline (see ``on_variant_changed``).
    Returns ``True`` if the override was written (or was already correct
    for this seat); ``False`` if the seat ID is unknown or the crowd
    payload is not loaded.
    """
    global _currently_hidden_seat
    if Usd is None:
        return False
    seat_map = _ensure_map()
    key = str(seat_id).strip()
    crowd_id = seat_map.get(key) or seat_map.get(key.upper())
    if crowd_id is None:
        return False

    instancer = _get_instancer()
    if instancer is None:
        return False

    baseline = _baseline_invisible_ids()
    if crowd_id not in baseline:
        baseline.append(crowd_id)
    _set_session_invisible_ids(baseline)
    _currently_hidden_seat = key
    print(f"[SEATED_CROWD_HL] Hid character for seat '{key}' "
          f"(crowd id {crowd_id})")
    return True


def restore() -> bool:
    """Drop the session-layer override so the variant value shows through.

    No-op if nothing is currently hidden. Returns ``True`` if an
    override was cleared.
    """
    global _currently_hidden_seat
    if Usd is None or _currently_hidden_seat is None:
        return False
    _clear_session_invisible_ids()
    prev = _currently_hidden_seat
    _currently_hidden_seat = None
    print(f"[SEATED_CROWD_HL] Restored character for seat '{prev}' "
          f"(session layer cleared)")
    return True


def on_variant_changed():
    """Re-apply the hide against the new variant baseline.

    Called by ``navmesh_route_extension/extension.py`` whenever
    ``seatedCrowdLayoutChanged`` fires. If a seat is currently held
    hidden, recompute and rewrite the union; otherwise no-op.
    """
    if _currently_hidden_seat is None:
        return
    # Re-resolve against the post-flip baseline.
    seat = _currently_hidden_seat
    # Drop our session opinion first so ``_baseline_invisible_ids`` does
    # not need to skip ``Sdf.SpecifierOver`` shenanigans, then re-hide.
    _clear_session_invisible_ids()
    hide_for_seat(seat)


def get_hidden_seat() -> Optional[str]:
    """Return the seat ID currently being hidden, or ``None``."""
    return _currently_hidden_seat
