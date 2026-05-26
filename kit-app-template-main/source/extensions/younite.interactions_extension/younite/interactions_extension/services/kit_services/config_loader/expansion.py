"""NPC / icon entry auto-expansion (synthetic pointer + click points)."""
from __future__ import annotations

from typing import List

from .... import usd_helpers
from .constants import NPC_KIT_ONLY_KEYS


def npc_config_for_web(npc_cfg: dict) -> dict:
    return {k: v for k, v in npc_cfg.items() if k not in NPC_KIT_ONLY_KEYS}


def expand_npc_entry(pt: dict) -> list:
    """Auto-expand a single NPC entry into pointer + click synthetic points."""
    npc_cfg = pt.get("npcConfig")
    if not isinstance(npc_cfg, dict):
        return [pt]

    _id = str(pt.get("id") or "").strip()
    pos_cfg = pt.get("position") or {}
    scene = pt.get("scene")
    trigger_cfg = pt.get("trigger") or {}
    approach_cfg = pt.get("approach")

    pointer_pt = {
        "id": f"{_id}__pointer",
        "label": npc_cfg.get("avatarName", _id),
        "interactionType": "npc",
        "category": "interactive",
        "scene": scene,
        "position": dict(pos_cfg),
        "trigger": dict(trigger_cfg),
        "_npc_pointer": True,
        "behaviors": [
            {"type": "projectable", "ui": {"style": "interactivePointer"}},
        ],
    }

    click_pt = {
        "id": f"{_id}__chat",
        "label": f"{npc_cfg.get('avatarName', _id)} Chat",
        "interactionType": "npc",
        "category": "interactive",
        "scene": scene,
        "position": {k: v for k, v in pos_cfg.items() if k != "positionOffset"},
        "trigger": {"type": "click", "activation": "always"},
        "behaviors": [
            {
                "type": "action",
                "actions": {
                    "onClick": [
                        {
                            "target": "web",
                            "action": "avatarChat.open",
                            "payload": npc_config_for_web(npc_cfg),
                        }
                    ]
                },
            }
        ],
    }
    if approach_cfg:
        click_pt["approach"] = dict(approach_cfg)

    return [pt, pointer_pt, click_pt]


def expand_icon_entry(pt: dict) -> List[dict]:
    """Auto-expand an icon entry into pointer + click synthetic points."""
    icon_cfg = pt.get("iconConfig")
    if not isinstance(icon_cfg, dict):
        return [pt]

    _id = str(pt.get("id") or "").strip()
    pos_cfg = pt.get("position") or {}
    scene = pt.get("scene")
    trigger_cfg = pt.get("trigger") or {}

    pointer_pt = {
        "id": f"{_id}__pointer",
        "label": icon_cfg.get("iconName", _id),
        "interactionType": "icon",
        "category": "interactive",
        "scene": scene,
        "position": dict(pos_cfg),
        "trigger": dict(trigger_cfg),
        "_icon_pointer": True,
        "behaviors": [
            {"type": "projectable", "ui": {"style": "interactivePointer"}},
        ],
    }

    mt = icon_cfg.get("mediaType")
    if mt == "spatialSound":
        action_name = "spatialSound.open"
    elif mt == "video360":
        action_name = "video360.open"
    elif mt == "coinPoi":
        action_name = "coinPoi.open"
    else:
        action_name = "videobook.open"

    click_payload = dict(icon_cfg)
    prim_path = usd_helpers.resolve_prim_path_from_config(pos_cfg)
    if prim_path:
        click_payload["primPath"] = prim_path

    click_pt = {
        "id": f"{_id}__click",
        "label": f"{icon_cfg.get('iconName', _id)} Click",
        "interactionType": "icon",
        "category": "interactive",
        "scene": scene,
        "position": {k: v for k, v in pos_cfg.items() if k != "positionOffset"},
        "trigger": {"type": "click", "activation": "always"},
        "behaviors": [
            {
                "type": "action",
                "actions": {
                    "onClick": [
                        {
                            "target": "web",
                            "action": action_name,
                            "payload": click_payload,
                        }
                    ]
                },
            }
        ],
    }

    return [pt, pointer_pt, click_pt]
