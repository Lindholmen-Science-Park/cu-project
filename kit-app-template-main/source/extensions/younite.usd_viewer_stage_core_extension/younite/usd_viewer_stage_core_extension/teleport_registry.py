"""
Registry so other extensions (e.g. player_core PhysxBootstrap) can use
TeleportService for initial/scene-switch placement without double-placement.
StageCore sets the service on startup and clears on shutdown.
"""

_teleport_service = None


def set_teleport_service(service):
    global _teleport_service
    _teleport_service = service


def get_teleport_service():
    return _teleport_service
