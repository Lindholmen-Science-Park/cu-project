"""``interactions.json`` loader package — types, parse, session-layer attach."""

from .loader import ConfigLoader
from .types import BoundsType, LoadedConfig, SpatialTriggerSpec

__all__ = ["BoundsType", "ConfigLoader", "LoadedConfig", "SpatialTriggerSpec"]
