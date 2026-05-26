"""NavMesh area cost helpers."""

from typing import Dict, Optional


def any_cost_above_default(costs: Optional[Dict[str, float]]) -> bool:
    """True if any cost value is meaningfully above the default 1.0."""
    if not costs:
        return False
    return any(v > 1.05 for v in costs.values())
