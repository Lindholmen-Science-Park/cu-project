"""
Build the ambient-emitter payload from ``source/data/sound_emitters.json``.

The JSON file is the source of truth for **which** emitters exist and **how**
they sound (file, radius, volume, …).  The USD scene is responsible only for
**where** each emitter is — every JSON entry must have a matching empty Xform
named ``id`` somewhere under ``/World``.  Parent that Xform under an NPC or
any moving prim and the sound follows automatically.

JSON schema (one entry):

    {
      "id": "sound_emitter_fountain_1",   // also the Xform name (recursive lookup under /World)
      "file": "fountain_loop.wav",         // filename inside source/data/nucleus/sounds/
      "scene": ["main_scene"],             // optional; omit = all scenes
      "radius": 1500,                      // optional, cm; default 2000
      "refDistance": 300,                  // optional, cm; default 200
      "volume": 0.8,                       // optional, 0..1; default 1.0
      "loop": true,                        // optional; default true
      "startDelaySec": 0.0,                // optional; default 0
      "positionOffset": [0, 0, 0]          // optional cm offset on top of world transform
    }

Returns ``[]`` for every "nothing to do" branch (missing file, empty list,
missing stage, no matching prims) so the browser ambient engine stays dormant.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


CONFIG_RELATIVE = ("source", "data", "sound_emitters.json")

_DEFAULTS = {
    "radius": 2000.0,
    "refDistance": 200.0,
    "volume": 1.0,
    "loop": True,
    "startDelaySec": 0.0,
}


# ── stage / config helpers ────────────────────────────────────────────────

def get_current_stage() -> Optional[object]:
    try:
        import omni.usd
        return omni.usd.get_context().get_stage()
    except Exception:
        return None


def get_config_path() -> str:
    """Locate ``sound_emitters.json`` by probing upward from this file."""
    try:
        here = Path(__file__).resolve()
        probe = here
        for _ in range(12):
            if probe.name.lower() == "kit-app-template-main":
                candidate = probe.joinpath(*CONFIG_RELATIVE)
                if candidate.exists():
                    return str(candidate)
            if probe.name.lower() == "source":
                candidate = probe.joinpath(*CONFIG_RELATIVE[1:])
                if candidate.exists():
                    return str(candidate)
            if probe.parent == probe:
                break
            probe = probe.parent
    except Exception:
        pass
    return ""


def _scene_candidates_from_stage(stage) -> Set[str]:
    out: Set[str] = set()
    if not stage:
        return out
    try:
        root = stage.GetRootLayer()
        ident = str(getattr(root, "identifier", "") or "").strip()
        if ident:
            out.add(ident)
            base = os.path.basename(ident)
            if base:
                out.add(base)
                if "." in base:
                    out.add(base.rsplit(".", 1)[0])
    except Exception:
        pass
    return out


def _matches_scene(entry_scene, candidates: Set[str]) -> bool:
    if entry_scene is None:
        return True
    if isinstance(entry_scene, list):
        return any(str(v) in candidates for v in entry_scene)
    return str(entry_scene) in candidates


def _load_json(path: str) -> Optional[dict]:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"[sound_emitter] failed to read {path}: {e}")
        return None


# ── prim lookup ──────────────────────────────────────────────────────────

def _find_prim_by_name(stage, name: str):
    """Recursive search under ``/World`` for the first prim whose leaf name matches.

    Returns ``None`` if no match — caller logs a warning so authoring typos
    are visible.
    """
    if not name:
        return None
    try:
        from pxr import Usd
    except Exception:
        return None
    try:
        world = stage.GetPrimAtPath("/World")
        if not (world and world.IsValid()):
            return None
        for prim in Usd.PrimRange(world):
            if prim.GetName() == name:
                return prim
    except Exception:
        pass
    return None


def _world_position(prim, cache, offset: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    try:
        m = cache.GetLocalToWorldTransform(prim)
        t = m.ExtractTranslation()
        return (
            float(t[0]) + float(offset[0]),
            float(t[1]) + float(offset[1]),
            float(t[2]) + float(offset[2]),
        )
    except Exception:
        return None


# ── public API ───────────────────────────────────────────────────────────

def collect_sound_emitters(stage) -> List[Dict[str, Any]]:
    """Build the browser-bound emitter payload from the JSON file + USD positions.

    Returns ``[]`` when the JSON is missing, empty, the stage is missing, or
    no JSON entry matches the current scene — keeping the ambient engine
    dormant until real content arrives.
    """
    if stage is None:
        return []

    try:
        from pxr import Usd, UsdGeom
    except Exception:
        return []

    cfg = _load_json(get_config_path())
    if not cfg:
        return []

    raw_entries = cfg.get("emitters") if isinstance(cfg, dict) else None
    if not isinstance(raw_entries, list) or not raw_entries:
        return []

    candidates = _scene_candidates_from_stage(stage)
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    emitters: List[Dict[str, Any]] = []

    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue

        emitter_id = str(entry.get("id") or "").strip()
        file_val = str(entry.get("file") or "").strip()
        if not emitter_id or not file_val:
            print(f"[sound_emitter] skipping entry with missing id/file: {entry!r}")
            continue

        if not _matches_scene(entry.get("scene"), candidates):
            continue

        prim = _find_prim_by_name(stage, emitter_id)
        if prim is None:
            print(f"[sound_emitter] no Xform named '{emitter_id}' found under /World — skipping")
            continue

        offset_raw = entry.get("positionOffset") or [0, 0, 0]
        try:
            offset = (float(offset_raw[0]), float(offset_raw[1]), float(offset_raw[2]))
        except Exception:
            offset = (0.0, 0.0, 0.0)

        pos = _world_position(prim, cache, offset)
        if pos is None:
            print(f"[sound_emitter] failed to read world transform for '{emitter_id}' — skipping")
            continue

        emitters.append({
            "id": emitter_id,
            "primPath": str(prim.GetPath()),
            "file": file_val,
            "pos": [pos[0], pos[1], pos[2]],
            "radius": float(entry.get("radius", _DEFAULTS["radius"])),
            "refDistance": float(entry.get("refDistance", _DEFAULTS["refDistance"])),
            "volume": float(entry.get("volume", _DEFAULTS["volume"])),
            "loop": bool(entry.get("loop", _DEFAULTS["loop"])),
            "startDelaySec": float(entry.get("startDelaySec", _DEFAULTS["startDelaySec"])),
        })

    return emitters
