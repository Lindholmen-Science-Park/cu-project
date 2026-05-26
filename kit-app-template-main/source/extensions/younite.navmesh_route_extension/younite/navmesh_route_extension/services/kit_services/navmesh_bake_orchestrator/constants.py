"""Walking agent keys and wheelchair preset — NavMesh bake orchestrator."""

from __future__ import annotations

from typing import Dict

# Keys read from customLayerData.navmeshSettings
AGENT_SETTING_KEYS = (
    "agentMaxFloorSlope",
    "agentMaxRadius",
    "agentMaxStepHeight",
    "agentMinHeight",
    "agentMinIslandRadius",
    "agentMinRadius",
    "agentSamplingDistance",
)

# Wheelchair agent settings — explicit; never inherits from scene defaults.
WHEELCHAIR_AGENT_SETTINGS: Dict[str, float] = {
    "agentMaxFloorSlope": 45.0,
    "agentMaxRadius": 50.0,
    "agentMaxStepHeight": 5.0,
    "agentMinHeight": 150.0,
    "agentMinIslandRadius": 500.0,
    "agentMinRadius": 20.0,
    "agentSamplingDistance": 20.0,
}
