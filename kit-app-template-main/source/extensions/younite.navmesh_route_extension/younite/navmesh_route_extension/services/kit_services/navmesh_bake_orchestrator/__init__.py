"""
NavMesh Bake Orchestrator

Centralises the rebake lifecycle so that every bake automatically
includes all currently-active area providers (cameras, incidents,
sound areas, etc.). Callers only need to call
``orchestrator.request_rebake()`` — they never have to know about
other providers.

Provider protocol
-----------------
Any object with ``name``, ``is_active()``, ``prepare_for_bake()``,
``after_bake()``, and ``remove_areas()`` can be registered.
"""

from __future__ import annotations

from .constants import AGENT_SETTING_KEYS, WHEELCHAIR_AGENT_SETTINGS
from .diagnostics import log_baked_navmesh_areas
from .orchestrator import NavMeshBakeOrchestrator
from .protocol import NavMeshAreaProvider
from .providers import (
    CameraAreaProvider,
    CameraDepthObstacleProvider,
    DEPTH_OBSTACLES_ROOT,
    IncidentAreaProvider,
    SoundAreaProvider,
    set_camera_depth_areas_visible,
)

__all__ = [
    "AGENT_SETTING_KEYS",
    "CameraAreaProvider",
    "CameraDepthObstacleProvider",
    "DEPTH_OBSTACLES_ROOT",
    "IncidentAreaProvider",
    "NavMeshAreaProvider",
    "NavMeshBakeOrchestrator",
    "SoundAreaProvider",
    "WHEELCHAIR_AGENT_SETTINGS",
    "log_baked_navmesh_areas",
    "set_camera_depth_areas_visible",
]
