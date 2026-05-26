"""Feature commands service package.

Re-exports :class:`FeatureCommandsService` so existing imports
(``from .feature_commands_service import FeatureCommandsService``)
keep working after the 1474-line monolith was split into focused
submodules:

* :mod:`.service` — thin orchestrator (event wiring, shared primitives,
  small inline handlers)
* :mod:`.view_switcher` — first-person entry + non-FP view transitions
* :mod:`.fp_state` — first-person state capture / restore
* :mod:`.directions_utils` — pure helpers shared by the directions flows
* :mod:`.map_marker_directions` — bird-eye directions panel (POI +
  pin-anywhere)
* :mod:`.seat_directions` — bird-eye seat directions + seat teleport
"""

from .service import FeatureCommandsService

__all__ = ["FeatureCommandsService"]
