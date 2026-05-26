"""Read walking-mode agent defaults from the root layer."""

from __future__ import annotations

from typing import Dict

from .constants import AGENT_SETTING_KEYS


def read_walking_agent_defaults_from_stage() -> Dict[str, float]:
    """Return agent settings from ``customLayerData.navmeshSettings`` (walking preset).

    Empty dict if stage or settings are missing.
    """
    import omni.usd

    ctx = omni.usd.get_context()
    stage = ctx.get_stage() if ctx else None
    if not stage:
        return {}

    root_layer = stage.GetRootLayer()
    custom_data = root_layer.customLayerData or {}
    nav_settings = custom_data.get("navmeshSettings", {})

    defaults: Dict[str, float] = {}
    for key in AGENT_SETTING_KEYS:
        val = nav_settings.get(key)
        if val is not None:
            defaults[key] = float(val)
    return defaults
