"""POI data directory discovery, JSON loading, and route-flag data root."""

from __future__ import annotations

import json
import os

from .wiring import NavmeshWireContext

_MARKER_FILE = "restroom_data.json"


def find_data_dir() -> str | None:
    """Locate source/data/ using the same anchor strategy as interactions_extension."""
    from pathlib import Path

    # Same walk as extension.py (``__file__`` here lives under ``events/``).
    probe = Path(__file__).resolve().parent.parent
    for _ in range(12):
        if probe.name.lower() == "source" and (probe / "data" / _MARKER_FILE).exists():
            return str(probe / "data")
        if probe.name.lower() == "kit-app-template-main" and (
            probe / "source" / "data" / _MARKER_FILE
        ).exists():
            return str(probe / "source" / "data")
        for sub in ("data", os.path.join("source", "data")):
            c = probe / sub
            if c.is_dir() and (c / _MARKER_FILE).exists():
                return str(c)
        if probe.parent == probe:
            break
        probe = probe.parent
    cwd_candidate = os.path.normpath(os.path.join(os.getcwd(), "source", "data"))
    if os.path.isfile(os.path.join(cwd_candidate, _MARKER_FILE)):
        return cwd_candidate
    return None


def load_poi_state(ctx: NavmeshWireContext) -> None:
    """Populate ``ctx.poi_configs`` and ``ctx.waypoint_route_ids``; wire route-flag root."""
    data_dir = find_data_dir()
    if data_dir:
        print(f"[navmesh_route] POI data directory: {data_dir}")
    else:
        print(
            f"[navmesh_route] WARNING: Could not find POI data directory "
            f"(events package cwd={os.getcwd()})"
        )

    try:
        from ..scripts.navmesh_shortest_path import set_route_flag_data_root

        set_route_flag_data_root(data_dir)
    except Exception as _e:
        print(f"[navmesh_route] route flag data root wiring failed: {_e}")

    poi_configs = {
        "exit": {
            "prefix": "exit_point_",
            "route_id": "exit_nav",
            "max_results": 10,
            "data_file": "exit_data.json",
        },
        "restroom": {
            "prefix": "restroom_",
            "route_id": "poi_nav",
            # None — return every in-use restroom so the web filter is not limited
            # to the nearest N; RestroomWidget caps the unfiltered list at 10.
            "max_results": None,
            "use_waypoints": True,
            "data_file": "restroom_data.json",
        },
        "quiet_zone": {
            "prefix": "quiet_zone_",
            "route_id": "quiet_zone_nav",
            "max_results": 10,
            "use_waypoints": True,
            "data_file": "quiet_zone_data.json",
        },
    }

    for cfg in poi_configs.values():
        df = cfg.get("data_file")
        if df:
            cfg["_data_lookup"] = _load_poi_data_file(data_dir, df)

    ctx.poi_configs = poi_configs
    ctx.waypoint_route_ids = frozenset(
        cfg["route_id"]
        for cfg in poi_configs.values()
        if cfg.get("use_waypoints") and "route_id" in cfg
    )


def _load_poi_data_file(data_dir: str | None, filename: str) -> dict:
    """Load source/data/<filename> -> {xform_id: {full entry dict}}."""
    if not data_dir:
        return {}
    path = os.path.join(data_dir, filename)
    if not os.path.isfile(path):
        print(f"[navmesh_route] POI data file not found: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            print(f"[navmesh_route] POI data file is not a JSON array: {path}")
            return {}
        lookup = {}
        for entry in entries:
            xid = entry.get("xform_id")
            if xid:
                lookup[xid] = entry
        print(f"[navmesh_route] Loaded {len(lookup)} POI entries from {filename}")
        return lookup
    except Exception as e:
        print(f"[navmesh_route] Failed to load POI data {path}: {e}")
        return {}


def discover_pois(prefix: str, data_lookup: dict | None = None) -> list[str]:
    """Discover /World prims by name prefix, gated by data lookup."""
    try:
        import omni.usd

        ctx = omni.usd.get_context()
        stage = ctx.get_stage() if ctx else None
        if not stage:
            return []
        world_prim = stage.GetPrimAtPath("/World")
        if not world_prim or not world_prim.IsValid():
            return []
        refs = []
        for child in world_prim.GetChildren():
            name = child.GetName()
            if not name.startswith(prefix) or not child.IsValid():
                continue
            if data_lookup is not None:
                entry = data_lookup.get(name)
                if entry is None:
                    print(
                        f"[navmesh_route] WARNING: orphan xForm '/World/{name}' "
                        f"has no data entry — consider removing from layer"
                    )
                    continue
                if not entry.get("in_use", True):
                    continue
            refs.append(child.GetPath().pathString)
        refs.sort()
        return refs
    except Exception as e:
        print(f"[navmesh_route] _discover_pois error: {e}")
        return []


def enrich_results(results: list, data_lookup: dict | None) -> list:
    """Attach metadata from data lookup to route result entries."""
    if not data_lookup:
        return results
    for entry in results:
        prim_path = entry.get("exitRef", "")
        prim_name = prim_path.rsplit("/", 1)[-1] if isinstance(prim_path, str) else ""
        meta = data_lookup.get(prim_name)
        if meta:
            entry["metadata"] = dict(meta)
    return results
