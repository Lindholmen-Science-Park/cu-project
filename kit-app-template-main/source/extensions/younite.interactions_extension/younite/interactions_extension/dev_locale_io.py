"""Helpers for writing viewer locale JSON from Kit (Media Admin \"Save via Kit\")."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def resolve_interactions_config_path(settings) -> str:
    """Match the same path resolution as :meth:`ConfigLoader.get_config_path` in ``services/kit_services/config_loader/loader.py``."""
    try:
        if settings:
            p = str(settings.get("/exts/younite.interactions_extension/data_file") or "").strip()
            if p:
                return p
    except Exception:
        pass
    try:
        here = Path(__file__).resolve()
        probe = here
        for _ in range(12):
            if probe.name.lower() == "source" and (probe / "data" / "interactions.json").exists():
                return str(probe / "data" / "interactions.json")
            if probe.name.lower() == "kit-app-template-main" and (
                probe / "source" / "data" / "interactions.json"
            ).exists():
                return str(probe / "source" / "data" / "interactions.json")
            if probe.parent == probe:
                break
            probe = probe.parent
    except Exception:
        pass
    return ""


def locale_json_path_from_interactions(interactions_path: str, locale: str) -> Optional[Path]:
    """``repo/web-viewer-sample-main/src/i18n/locales/{locale}.json`` next to kit-app."""
    try:
        p = Path(interactions_path).resolve()
        # .../kit-app-template-main/source/data/interactions.json
        kit_root = p.parent.parent.parent
        repo_root = kit_root.parent
        out = repo_root / "web-viewer-sample-main" / "src" / "i18n" / "locales" / f"{locale}.json"
        if out.is_file():
            return out
    except Exception:
        pass
    return None


def merge_interactions_strings(
    root: Dict[str, Any],
    patch_interactions: Dict[str, Any],
) -> None:
    """Deep-merge ``patch_interactions`` under root['interactions']."""
    if "interactions" not in root or not isinstance(root["interactions"], dict):
        root["interactions"] = {}
    base = root["interactions"]
    for key, val in patch_interactions.items():
        if not isinstance(val, dict):
            base[key] = val
            continue
        if key not in base or not isinstance(base[key], dict):
            base[key] = dict(val)
        else:
            base[key].update(val)


def write_locale_patch(
    *,
    interactions_path: str,
    locale: str,
    patch_interactions: Dict[str, Any],
) -> Tuple[bool, str]:
    path = locale_json_path_from_interactions(interactions_path, locale)
    if not path:
        return False, "locale file not found next to repo layout"

    try:
        import json

        raw_text = path.read_text(encoding="utf-8")
        root = json.loads(raw_text)
        if not isinstance(root, dict):
            return False, "locale JSON root must be an object"
        merge_interactions_strings(root, patch_interactions)
        path.write_text(
            json.dumps(root, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        return False, str(e)
    return True, str(path)
