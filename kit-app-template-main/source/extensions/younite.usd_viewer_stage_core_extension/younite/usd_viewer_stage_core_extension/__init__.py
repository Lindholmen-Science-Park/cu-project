"""
Stage core: stage loading, stage management, readiness state, and init timing.
"""

from .extension import StageCoreExtension
from .services.core_services.geo_coordinate_service import get_geo_coordinate_service
from .services.core_services.geo_teleport_transform import latlon_to_scene_xyz_for_teleport

__all__ = [
    "StageCoreExtension",
    "get_geo_coordinate_service",
    "latlon_to_scene_xyz_for_teleport",
]

