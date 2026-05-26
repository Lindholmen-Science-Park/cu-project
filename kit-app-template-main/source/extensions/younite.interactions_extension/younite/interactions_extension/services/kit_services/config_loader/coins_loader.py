"""POI coin (round-sign) iconGroup expansion.

Coin **rendering** is driven entirely by the xForm name in
``coins_layer.usda`` plus ``coins_registry.json`` — the POI JSON files
(``restroom_data.json``, ``kiosk_data.json``, …) are **optional metadata**
for the UI info card and never gate whether a coin appears in the world.
A coin with no matching JSON row still renders (same UX as a bare exit
coin); it just opens an info card with the leaf name as title and no
extra rows. ``in_use: false`` likewise no longer hides the coin — it is
metadata for the toilet/quiet-zone state, not a render gate.

Naming for coin xForms in ``coins_layer.usda`` (see :func:`_resolve_coin_name`):

1. **Variant** — ``coin_<poi_id_hint>_<coin_type>`` where ``<coin_type>``
   is a key in ``coins_registry.json``. Longest-suffix match handles
   multi-word types like ``changing_table`` and ``emergency_exit``.
   Examples: ``coin_restroom_02_accessible``,
   ``coin_restroom_12_changing_table``, ``coin_anywhere_unisex``.

2. **Simple** — ``coin_<category>_<digits>`` where ``<category>`` is a
   key in :data:`_CATEGORY_TO_COIN_TYPE`. The leading category token
   maps directly to a registry coin_type. Examples: ``coin_kiosk_01``
   (→ ``kiosk``), ``coin_elevator_02`` (→ ``elevator``),
   ``coin_ticket_office_01`` (→ ``ticket_office``), ``coin_exit_point_05``
   (→ ``emergency_exit``).

   Exit coins use ``coin_exit_point_*`` (paired with floor anchors
   ``exit_point_*`` in ``exit_points_layer.usda``); JSON ``xform_id``
   remains ``exit_point_*``.

The ``<poi_id_hint>`` portion (whatever sits before the registry suffix
in the variant form, or the full ``<category>_<digits>`` in the simple
form) is looked up in the union of POI data files. If a row matches,
its dict is forwarded as ``iconConfig.metadata`` and surfaces in
:file:`PoiInfoCard.tsx`; if no row matches, ``metadata`` is ``{}`` and
the coin still renders.

For each valid coin xForm the loader synthesises a single ``icon``-shaped
entry with ``iconConfig.mediaType = "coinPoi"``. The standard
:func:`expansion.expand_icon_entry` then auto-creates the click sub-point
that dispatches the ``coinPoi.open`` web action, and the entry is
registered in the icon registry so the existing ``nearestIcon`` tracker
drives the bottom-pill :file:`IconBubbleOverlay` (same UX as spatial-sound
and 360° video icons).

Side-effects: attaches the registry coin asset as a payload + invisible
``Cube "Collider"`` child on the coin xForm via the shared
:mod:`session_authoring` helpers — same path used by spatial-sound icons.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .... import usd_helpers
from . import expansion as exp
from . import session_authoring as sess


# POI metadata files merged into a single ``xform_id -> entry`` lookup.
# **Optional** — coins render with empty metadata when no row matches.
# Kept local so this loader does not import navmesh_route_extension.
_POI_DATA_FILES: Dict[str, str] = {
    "restroom": "restroom_data.json",
    "quiet_zone": "quiet_zone_data.json",
    "exit": "exit_data.json",
    "ticket_office": "ticket_office_data.json",
    "kiosk": "kiosk_data.json",
    "elevator": "elevator_data.json",
}

_COIN_NAME_PREFIX = "coin_"

# Simple-form ``coin_<category>_<digits>`` resolution table.
#
# Maps the leading category token (everything before the trailing
# ``_<digits>``) to its ``coins_registry.json`` coin_type. Lets
# ``coin_kiosk_01`` / ``coin_exit_point_05`` etc. resolve their asset
# from the xform name alone — no JSON row required.
#
# ``restroom`` and ``quiet_zone`` are intentionally absent: those POI
# categories support multiple coin variants per location (unisex /
# women / accessible / changing_table) and **must** use the explicit
# variant form ``coin_<poi_id>_<coin_type>``.
_CATEGORY_TO_COIN_TYPE: Dict[str, str] = {
    "kiosk": "kiosk",
    "elevator": "elevator",
    "ticket_office": "ticket_office",
    "exit_point": "emergency_exit",
}


def _load_json(abs_path: str) -> Optional[dict]:
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        print(f"[interactions] coins: failed to read {abs_path}: {ex}")
        return None


def _coerce_spin_enabled(value: Any, *, default: bool = True) -> bool:
    """JSON-friendly truthiness for ``spinEnabled`` flags."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("false", "0", "no", "off", "none"):
            return False
        if s in ("true", "1", "yes", "on"):
            return True
        return default
    return default


def _load_coin_registry(data_root) -> Tuple[Dict[str, Dict[str, Any]], bool]:
    """Load ``coins_registry.json`` → ``(coin_types, default_spin_enabled)``."""
    if not data_root:
        return {}, True
    path = str((data_root / "coins_registry.json").resolve())
    if not os.path.isfile(path):
        return {}, True
    raw = _load_json(path) or {}
    types = raw.get("coinTypes")
    if not isinstance(types, dict):
        return {}, _coerce_spin_enabled(raw.get("spinEnabled"), default=True)
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in types.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        out[k.strip()] = dict(v)
    default_spin = _coerce_spin_enabled(raw.get("spinEnabled"), default=True)
    return out, default_spin


def _load_poi_index(
    data_root,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """Build a ``xform_id -> entry`` map and a ``xform_id -> poiType`` map."""
    entries: Dict[str, Dict[str, Any]] = {}
    types: Dict[str, str] = {}
    if not data_root:
        return entries, types
    for poi_type, filename in _POI_DATA_FILES.items():
        path = str((data_root / filename).resolve())
        if not os.path.isfile(path):
            continue
        raw = _load_json(path) or {}
        rows = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            rows = raw if isinstance(raw, list) else []
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            xid = str(entry.get("xform_id") or "").strip()
            if not xid:
                continue
            entries[xid] = entry
            types[xid] = poi_type
    return entries, types


def _load_shortcuts_groups(data_root) -> Dict[str, Dict[str, Any]]:
    """``shortcuts.json`` group id → group dict (nodes, labels, prim paths)."""
    if not data_root:
        return {}
    path = str((data_root / "shortcuts.json").resolve())
    if not os.path.isfile(path):
        return {}
    raw = _load_json(path) or {}
    groups: Dict[str, Dict[str, Any]] = {}
    for g in raw.get("groups") or []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("id") or "").strip()
        if gid:
            groups[gid] = g
    return groups


def _elevator_ride_metadata(
    entry: Dict[str, Any],
    shortcuts_groups: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Other floors in the same shortcut group → ``elevator_ride`` for the web UI."""
    group_id = str(entry.get("shortcut_group_id") or "").strip()
    node_id = str(entry.get("shortcut_node_id") or "").strip()
    if not group_id or not node_id:
        return None
    group = shortcuts_groups.get(group_id)
    if not group:
        print(f"[interactions] coins: shortcut group '{group_id}' not in shortcuts.json")
        return None
    nodes_raw = group.get("nodes") or []
    nodes: Dict[str, Dict[str, Any]] = {}
    for n in nodes_raw:
        if isinstance(n, dict):
            nid = str(n.get("id") or "").strip()
            if nid:
                nodes[nid] = n
    destinations: List[Dict[str, Any]] = []
    for nid, node in nodes.items():
        if nid == node_id:
            continue
        prim_path = str(node.get("primPath") or "").strip()
        if not prim_path:
            continue
        dest: Dict[str, Any] = {
            "node_id": nid,
            "prim_path": prim_path,
            "label_en": str(node.get("labelEn") or nid),
        }
        i18n_key = str(node.get("i18nKey") or "").strip()
        if i18n_key:
            dest["i18n_key"] = i18n_key
        level = node.get("level")
        if isinstance(level, (int, float)):
            dest["level"] = int(level)
        destinations.append(dest)
    destinations.sort(
        key=lambda d: (
            d.get("level") is None,
            d.get("level", 0),
            str(d.get("label_en") or ""),
        )
    )
    if not destinations:
        return None
    return {
        "group_id": group_id,
        "current_node_id": node_id,
        "destinations": destinations,
    }


def _resolve_coin_name(
    leaf_name: str,
    registry: Dict[str, Dict[str, Any]],
) -> Optional[Tuple[str, str]]:
    """Resolve ``coin_*`` leaf name to ``(poi_id_hint, coin_type)`` from
    the name alone — POI JSON data is **not consulted** here.

    Two patterns, tried in order:

    1. **Variant** — ``coin_<poi_id_hint>_<coin_type>``: longest-suffix
       match against ``registry`` keys handles multi-word types like
       ``changing_table`` and ``emergency_exit``. The leading portion is
       returned as a hint for optional metadata lookup.

    2. **Simple** — ``coin_<category>_<digits>``: leading token must
       resolve through :data:`_CATEGORY_TO_COIN_TYPE`. The full
       ``<category>_<digits>`` becomes the metadata-lookup hint.

    Returns ``None`` if neither pattern resolves to a registry coin_type.
    Whether a matching POI row exists is irrelevant — that is checked at
    the call site purely to decorate the UI info card.
    """
    if not leaf_name.startswith(_COIN_NAME_PREFIX):
        return None
    rest = leaf_name[len(_COIN_NAME_PREFIX):]
    if not rest:
        return None

    # Variant: longest-suffix match against registry keys.
    for ct in sorted(registry.keys(), key=len, reverse=True):
        suffix = "_" + ct
        if rest.endswith(suffix):
            prefix = rest[: -len(suffix)]
            if prefix:
                return prefix, ct

    # Simple: trailing ``_<digits>`` and a known POI category prefix.
    last_us = rest.rfind("_")
    if last_us > 0:
        trailing = rest[last_us + 1:]
        prefix = rest[:last_us]
        if trailing.isdigit():
            ct = _CATEGORY_TO_COIN_TYPE.get(prefix)
            if ct and ct in registry:
                return rest, ct

    return None


def expand_coin_group_entry(
    pt: dict,
    *,
    data_root,
) -> List[dict]:
    """Expand a coin-flavored ``iconGroup`` template entry into per-coin points.

    Returns synthesised entries that flow through the standard parse loop
    (proximity speechBubble + click action). The coin USD asset is attached
    on the spot via session-layer payload.
    """
    pattern = str(pt.get("primNamePattern") or "").strip()
    if not pattern:
        return []

    # Comma-separated globs (e.g. ``coin_*,foo_*``) are merged de-duplicated by
    # prim path. ``coin_*`` includes ``coin_exit_point_*`` exit emergency prims.
    raw_patterns = [p.strip() for p in pattern.split(",") if p.strip()]
    seen_paths: set = set()
    matches: List[Tuple[str, str]] = []
    for p in raw_patterns:
        for prim_path, leaf_name in usd_helpers.find_xforms_by_glob(p):
            if prim_path in seen_paths:
                continue
            seen_paths.add(prim_path)
            matches.append((prim_path, leaf_name))
    if not matches:
        if usd_helpers.stage_has_world_children():
            print(f"[interactions] coin iconGroup '{pt.get('id')}': no Xforms match pattern '{pattern}'")
        return []

    registry, registry_spin_default = _load_coin_registry(data_root)
    if not registry:
        print("[interactions] coins: coins_registry.json missing or empty — coin xForms ignored")
        return []

    # POI metadata is OPTIONAL — coins render regardless. The lookups
    # below decorate the UI info card when a JSON row matches.
    poi_entries, poi_types = _load_poi_index(data_root)
    shortcuts_groups = _load_shortcuts_groups(data_root)

    base_trigger = dict(pt.get("trigger") or {})
    if not base_trigger:
        base_trigger = {"type": "proximity", "radiusMeters": 3, "activation": "always"}

    approach_cfg = pt.get("approach")
    scene = pt.get("scene")
    pos_offset = (pt.get("position") or {}).get("positionOffset")

    expanded: List[dict] = []
    for prim_path, leaf_name in matches:
        # ``find_xforms_by_glob`` uses ``fnmatch``, which is case-insensitive on
        # Windows — ``coin_*`` falsely matches prims like ``Coin_inner`` under
        # authored coin assets. Only treat lowercase ``coin_`` anchors.
        if not leaf_name.startswith(_COIN_NAME_PREFIX):
            continue
        parsed = _resolve_coin_name(leaf_name, registry)
        if parsed is None:
            print(
                f"[interactions] coins: '{leaf_name}' does not match "
                f"coin_<poi_id>_<coin_type> nor coin_<category>_<digits>, "
                f"skipping (registry keys: {list(registry.keys())})"
            )
            continue
        poi_id, coin_type = parsed

        coin_def = registry.get(coin_type)
        if not coin_def:
            # Defensive: _resolve_coin_name only returns coin_types in
            # the registry, but guards against future divergence.
            continue

        # POI JSON row is OPTIONAL — empty dict means the coin still
        # renders, the info card just shows the leaf name as title.
        # ``in_use: false`` is metadata for the toilet/quiet-zone state,
        # not a render gate; the web side decides how to surface it.
        entry = poi_entries.get(poi_id) or {}
        metadata = dict(entry)
        ride = _elevator_ride_metadata(entry, shortcuts_groups)
        if ride:
            metadata["elevator_ride"] = ride

        asset_rel = str(coin_def.get("asset") or "").strip()
        spin_axis_raw = str(coin_def.get("spinAxis") or "z").lower().strip()
        spin_enabled = _coerce_spin_enabled(
            coin_def.get("spinEnabled"), default=registry_spin_default
        )
        if spin_axis_raw in ("none", "off"):
            spin_enabled = False
        spin_axis = spin_axis_raw if spin_axis_raw in ("x", "y", "z") else "z"
        if asset_rel and data_root:
            mr = coin_def.get("modelRotation")
            if isinstance(mr, (list, tuple)) and len(mr) >= 3:
                model_rotation = (float(mr[0]), float(mr[1]), float(mr[2]))
            else:
                model_rotation = (0.0, 90.0, 0.0)
            ms = coin_def.get("modelScale")
            if isinstance(ms, (int, float)):
                s = float(ms)
                model_scale = (s, s, s)
            elif isinstance(ms, (list, tuple)) and len(ms) >= 3:
                model_scale = (float(ms[0]), float(ms[1]), float(ms[2]))
            else:
                model_scale = (0.25, 0.25, 0.25)
            sess.attach_coin_payload(
                prim_path,
                asset_rel,
                data_root=data_root,
                model_rotation_xyz=model_rotation,
                model_scale_xyz=model_scale,
                spin_axis=spin_axis,
                spin_enabled=spin_enabled,
            )

        poi_type = poi_types.get(poi_id, "")
        display_name = str(entry.get("display_name") or leaf_name)
        synth_id = f"coin_{leaf_name}"

        # Single icon-flavored entry. `expand_icon_entry` (same module that
        # handles spatial sound / 360° video / video book icons) auto-adds
        # the click sub-point and dispatches `coinPoi.open` because of
        # `mediaType: "coinPoi"`. The full iconConfig becomes the click
        # payload, so all POI fields the info card needs travel through.
        icon_entry = {
            "id": synth_id,
            "label": display_name,
            "interactionType": "icon",
            "category": "interactive",
            "scene": scene,
            "position": {
                "type": "xform",
                "primName": leaf_name,
                "positionOffset": pos_offset,
            },
            "trigger": dict(base_trigger),
            "iconConfig": {
                "iconId": synth_id,
                "iconName": leaf_name,
                "mediaType": "coinPoi",
                "title": display_name,
                "iconImage": str(coin_def.get("labelIcon") or ""),
                "poiType": poi_type,
                "xformId": poi_id,
                "coinType": coin_type,
                "displayName": display_name,
                "labelIcon": str(coin_def.get("labelIcon") or ""),
                "spinAxis": spin_axis,
                "spinEnabled": spin_enabled,
                "metadata": metadata,
            },
        }
        if approach_cfg:
            icon_entry["approach"] = dict(approach_cfg)

        # Run through the standard icon auto-expansion so the click
        # sub-point + action dispatch are generated identically to
        # spatial-sound / 360° video / video-book icons.
        expanded.extend(exp.expand_icon_entry(icon_entry))

    return expanded
