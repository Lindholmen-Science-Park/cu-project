"""
Waypoint Customization Extension for Omniverse Kit
Provides custom waypoint display with tooltips, thumbnails, and custom buttons
"""

from .extension import WaypointCustomizationManager, Extension

__all__ = ["WaypointCustomizationManager", "Extension"]

# Print to verify __init__.py is being executed
print("[Waypoint Extension] __init__.py executed", flush=True)
import sys
sys.stdout.flush()

