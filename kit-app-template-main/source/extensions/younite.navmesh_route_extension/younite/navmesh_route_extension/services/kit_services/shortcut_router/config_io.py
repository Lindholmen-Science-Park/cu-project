"""Resolve and load ``shortcuts.json``."""
from __future__ import annotations

import json
import os
from typing import Dict, Optional

from .constants import LOG_PREFIX


def _kit_services_dir() -> str:
    """``.../kit_services`` (parent of the ``shortcut_router`` package)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_shortcuts_config_path(config_path: Optional[str] = None) -> Optional[str]:
    if config_path and os.path.isfile(config_path):
        return config_path
    probe = _kit_services_dir()
    for _ in range(12):
        cand = os.path.normpath(
            os.path.join(probe, "source", "data", "shortcuts.json")
        )
        if os.path.isfile(cand):
            return cand
        cand2 = os.path.normpath(os.path.join(probe, "data", "shortcuts.json"))
        if os.path.isfile(cand2):
            return cand2
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    cwd_cand = os.path.normpath(
        os.path.join(os.getcwd(), "source", "data", "shortcuts.json")
    )
    return cwd_cand if os.path.isfile(cwd_cand) else None


def load_shortcuts_config_dict(config_path: Optional[str] = None) -> Optional[Dict]:
    path = resolve_shortcuts_config_path(config_path)
    if not path:
        print(f"{LOG_PREFIX} shortcuts.json not found; shortcuts disabled")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"{LOG_PREFIX} Failed to read {path}: {exc}")
        return None
