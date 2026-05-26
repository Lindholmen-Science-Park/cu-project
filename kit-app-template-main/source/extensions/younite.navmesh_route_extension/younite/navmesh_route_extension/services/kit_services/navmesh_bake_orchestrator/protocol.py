"""Provider protocol for NavMesh area sources."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NavMeshAreaProvider(Protocol):
    @property
    def name(self) -> str: ...

    def is_active(self) -> bool:
        """True when this provider's areas should be included in the bake."""
        ...

    def prepare_for_bake(self) -> None:
        """Ensure area prims exist on the nav layer (synchronous)."""
        ...

    def after_bake(self) -> None:
        """Post-bake cleanup (e.g. hide debug visuals)."""
        ...

    def remove_areas(self) -> None:
        """Delete area prims from the nav layer."""
        ...
