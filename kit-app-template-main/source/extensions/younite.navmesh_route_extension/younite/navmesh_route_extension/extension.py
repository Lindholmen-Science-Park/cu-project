"""Navmesh route Kit extension entry — slim orchestrator."""

from __future__ import annotations

import omni.ext

from .events import register_navmesh_route_events
from .extension_lifecycle import (
    shutdown_navmesh_route_services,
    startup_navmesh_route_services,
)


class NavMeshRouteExtension(omni.ext.IExt):
    """Navmesh route feature extension."""

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._initial_bake_task = None

        startup_navmesh_route_services(self)
        register_navmesh_route_events(self)

    def on_shutdown(self):
        shutdown_navmesh_route_services(self)
