"""Tunable constants and raw label tables for bird-eye pin placement."""

from __future__ import annotations

from typing import Dict

# Maximum horizontal distance (stage units = cm) from the click to the
# nearest waypoint / named spawn magnet for an in-arena pin. Larger values
# cover roof-centre → nearest entrance; smaller values reduce accidental
# snaps when clicking plaza/street geometry near the arena.
MAX_MAGNET_SNAP_XZ_CM: float = 2500.0  # 25 m

# Friendly display-name overrides for raw waypoints. `nav_waypoint_AB`
# reads as "A / B" to users. Missing entries fall through to the
# capitalised waypoint suffix.
WAYPOINT_LABELS: Dict[str, str] = {
    "nav_waypoint_entrance_01": "Entrance 1",
    "nav_waypoint_entrance_02": "Entrance 2",
    "nav_waypoint_entrance_03": "Entrance 3",
}

# Friendly labels for named spawn points that act as magnets.
SPAWN_POINT_LABELS: Dict[str, str] = {
    "PlayerSpawnPoint_Foyer": "Foyer",
    "PlayerSpawnPoint_Arena": "Arena",
    "PlayerSpawnPoint_Start": "Start",
    "PlayerSpawnPoint_Red": "Red",
}

SPAWN_PREFIX = "PlayerSpawnPoint_"
ENTRANCE_PREFIX = "nav_waypoint_entrance_"
