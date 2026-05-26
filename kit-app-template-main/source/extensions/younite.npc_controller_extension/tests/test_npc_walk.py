"""
NPC Controller — Quick Test Script
====================================
Paste this into Kit's Script Editor (Window > Script Editor) and press Run.

Spawns NPC capsules that patrol between their start/end points.
NPC definitions are loaded from config/npc_configs.json — edit that file
to add, remove, or reconfigure NPCs without touching this script.

Prerequisites:
  - main_scene.usda loaded
  - NavMesh baked (the navmesh_route_extension auto-bakes on player ready)
  - younite.npc_controller_extension enabled in the .kit file
"""
import json
import os

from younite.messaging_core_extension.message_utils import dispatch_to_events2

config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "npc_configs.json",
)

with open(config_path, "r") as f:
    config = json.load(f)

default_model = config.get("defaultModel")
defaults = {
    "speed": config.get("speed", 200),
    "loop": config.get("loop", True),
    "drawPath": config.get("drawPath", False),
}

for npc in config["npcs"]:
    payload = {**npc, **defaults}
    payload["model"] = npc.get("model", default_model)
    dispatch_to_events2("npcSpawn", payload)
    print(f"[test] npcSpawn dispatched: {npc['npcId']}  {npc['start']} -> {npc['end']}")

print(f"[test] All {len(config['npcs'])} NPCs spawned — capsules auto-created by the extension")
