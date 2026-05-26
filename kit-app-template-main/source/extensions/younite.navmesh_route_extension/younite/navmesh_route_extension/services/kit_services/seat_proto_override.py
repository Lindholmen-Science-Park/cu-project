"""Single owner of the seat-instancer's session-layer ``protoIndices`` opinion.

Both ``seat_highlight`` (single seat → green Highlight prototype) and
``seat_fold_state`` (every occupied seat → Down prototype) need to flip
prototype indices on the same PointInstancer at runtime. Doing the
``Set(IntArray(...))`` from each module independently means whichever
writes last overwrites the other — the user would lose the fold-state
the moment a seat-nav highlight is applied (or vice versa).

This module solves that by being the **only** writer of the session
layer's ``protoIndices`` opinion. Both callers register their per-seat
overrides through this module's ``set`` / ``clear`` API; this module
keeps the merged dictionary, recomputes the full array against the
current variant baseline, and writes it once. Highlight ranks above
fold-state via the priority field (``HIGHLIGHT_PRIORITY > FOLD_PRIORITY``)
so the Highlight prototype always wins for the seat-nav target, even if
fold-state separately wants it Down.

Prototype indices (must match ``generate_instancer.py``):
  0 = ChairOrangeUp     (default, upper tier)
  1 = ChairWhiteUp      (default, lower tier)
  2 = ChairOrangeDown   (occupied / nav target — upper tier)
  3 = ChairWhiteDown    (occupied / nav target — lower tier)
  4 = ChairHighlight    (green-glow nav target, Down geometry)

This module is a no-op (returns ``False``) if the seat instancer is not
loaded yet or ``pxr`` is unavailable.
"""

from typing import Dict, Optional, Tuple
import omni.usd

try:
    from pxr import Usd, UsdGeom, Vt
except ImportError:
    Usd = None
    UsdGeom = None
    Vt = None

INSTANCER_PATH = "/World/Skandinavium/seats_instanced/SeatInstancer"

# Priority — higher wins when multiple overrides target the same seat.
# FOLD_PRIORITY      — crowd-driven Down for occupied seats. Cleared in
#                      bulk on every density flip.
# NAV_VISITED_PRIORITY — "this seat was navigated to" Down state. Sits
#                      above FOLD so it survives crowd density flips
#                      (incl. crowd-off) but below HIGHLIGHT so the
#                      green highlight shows during an active route.
#                      Persists for the rest of the session.
# HIGHLIGHT_PRIORITY — green-glow nav target. Always wins.
FOLD_PRIORITY = 1
NAV_VISITED_PRIORITY = 5
HIGHLIGHT_PRIORITY = 10

# Up → Down prototype index lookup, mirrors generate_instancer.py.
PROTO_ORANGE_UP = 0
PROTO_WHITE_UP = 1
PROTO_ORANGE_DOWN = 2
PROTO_WHITE_DOWN = 3
_UP_TO_DOWN = {PROTO_ORANGE_UP: PROTO_ORANGE_DOWN,
               PROTO_WHITE_UP: PROTO_WHITE_DOWN}

# Internal state: { instance_idx: (proto_idx, priority) }
_overrides: Dict[int, Tuple[int, int]] = {}


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


def _baseline_proto_indices():
    """Return ``protoIndices`` from the strongest *non-session* opinion.

    Walking the property stack lets us see the variant's authored value
    even when our own session-layer override is in place — same trick
    ``seated_crowd_highlight`` uses for ``invisibleIds``.
    """
    instancer = _get_instancer()
    if instancer is None:
        return None
    stage = _get_stage()
    session = stage.GetSessionLayer()
    attr = instancer.GetProtoIndicesAttr()
    for spec in attr.GetPropertyStack(Usd.TimeCode.Default()):
        if spec.layer == session:
            continue
        default = spec.default
        if default is not None:
            return list(int(x) for x in default)
    return None


def _flush():
    """Recompute the merged array from the variant baseline + overrides
    and write it to the session layer (or clear the opinion when there
    are no overrides)."""
    instancer = _get_instancer()
    if instancer is None or Usd is None:
        return False

    stage = _get_stage()
    session = stage.GetSessionLayer()

    if not _overrides:
        with Usd.EditContext(stage, session):
            instancer.GetProtoIndicesAttr().Clear()
        return True

    baseline = _baseline_proto_indices()
    if baseline is None:
        return False

    merged = list(baseline)
    n = len(merged)
    for idx, (proto_idx, _prio) in _overrides.items():
        if 0 <= idx < n:
            merged[idx] = proto_idx

    with Usd.EditContext(stage, session):
        instancer.GetProtoIndicesAttr().Set(Vt.IntArray(merged))
    return True


def set_overrides(updates: Dict[int, Tuple[int, int]],
                  clear_priority: Optional[int] = None) -> bool:
    """Bulk-replace overrides at one priority level.

    Used by ``seat_fold_state`` to publish "all occupied seats" in a
    single flush. ``clear_priority`` (when set) drops every existing
    override at that priority before applying ``updates`` — so flipping
    crowd density doesn't leave stale Down-state on seats that just
    became empty. Highlight overrides at higher priority are unaffected.
    """
    if clear_priority is not None:
        for idx in [k for k, (_p, prio) in _overrides.items()
                    if prio == clear_priority]:
            del _overrides[idx]
    for idx, (proto_idx, prio) in updates.items():
        existing = _overrides.get(idx)
        # Only overwrite when the incoming priority is >= existing.
        if existing is None or prio >= existing[1]:
            _overrides[idx] = (proto_idx, prio)
    return _flush()


def set_one(instance_idx: int, proto_idx: int, priority: int) -> bool:
    """Apply a single override. Used by ``seat_highlight``."""
    existing = _overrides.get(instance_idx)
    if existing is not None and priority < existing[1]:
        return False
    _overrides[instance_idx] = (proto_idx, priority)
    return _flush()


def clear_one(instance_idx: int, priority: int) -> bool:
    """Drop a single override if its priority matches.

    The priority match guards against ``seat_highlight`` clobbering
    ``seat_fold_state``'s Down-state on the same seat: clearing the
    highlight (priority 10) leaves a fold-state opinion (priority 1)
    untouched if it has one, otherwise the seat reverts to Up.
    """
    existing = _overrides.get(instance_idx)
    if existing is None:
        return False
    if existing[1] != priority:
        return False
    del _overrides[instance_idx]
    return _flush()


def get_baseline_proto(instance_idx: int) -> Optional[int]:
    """Return the variant-baseline proto index at ``instance_idx``.

    Used by callers (``seat_highlight``) that want to derive the
    matching Down prototype without knowing the seat's tier.
    """
    baseline = _baseline_proto_indices()
    if baseline is None or instance_idx < 0 or instance_idx >= len(baseline):
        return None
    return int(baseline[instance_idx])


def set_down_for_seat(instance_idx: int, priority: int) -> bool:
    """Apply a Down-state override based on the seat's baseline tier.

    Looks up baseline proto at ``instance_idx`` (0=OrangeUp / 1=WhiteUp)
    and writes the matching Down proto (2/3) at ``priority``. No-op if
    the baseline is missing or the seat is not a known Up prototype
    (e.g. a wheelchair or companion outside the Up/Down convention).
    """
    base = get_baseline_proto(instance_idx)
    if base is None:
        return False
    down = _UP_TO_DOWN.get(base)
    if down is None:
        return False
    return set_one(instance_idx, down, priority)


def reapply() -> bool:
    """Re-flush against the current baseline.

    Call after the seating variant changes (variant flip rewrites the
    baseline ``protoIndices`` array). Override indices are stable
    across variants because the seat instance order is variant-stable
    in the generator.
    """
    return _flush()


def reset():
    """Drop every override and clear the session-layer opinion."""
    _overrides.clear()
    _flush()


def get_active_overrides() -> Dict[int, Tuple[int, int]]:
    """Diagnostic snapshot of the current override map."""
    return dict(_overrides)
