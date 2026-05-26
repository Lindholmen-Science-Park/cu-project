"""
NavMesh Mode Cache — holds two baked ``INavMesh`` handles (wheelchair + walking)
and swaps between them instantly on mode change.

Kit exposes a single "active" NavMesh via ``inav.get_navmesh()``.  However, the
handle returned is reference-counted: as long as Python keeps a reference the
underlying mesh data stays alive in memory even after a new bake overwrites
the active mesh.  We exploit this:

    1. Bake wheelchair settings, grab handle.
    2. Bake walking settings, grab handle.
    3. Both meshes now live side-by-side in memory; walking is "active"
       (returned by ``inav.get_navmesh()``) because it was baked last.

Route queries pass the selected handle as ``navmesh_override`` into
``calculate_path_points`` so switching mode becomes an instant pointer swap
instead of a 10-20 s rebake.

Orchestrator-driven rebakes (incidents / area providers) re-run
``bake_both_modes`` so every cached handle picks up the new obstacles.
"""

from __future__ import annotations

from typing import Any, Optional

import omni.kit.app as kit_app

from .navmesh_bake_utils import change_agent_settings_and_rebake as _change_agent_settings_and_rebake


_VALID_MODES = ("walking", "wheelchair")
_BAKE_RETRY_COUNT = 3


class NavMeshModeCache:
    """Caches per-mode baked NavMesh handles and exposes the active one.

    Wheelchair is baked first, walking last — so the last bake leaves
    ``inav.get_navmesh()`` pointing at the walking mesh (matching the default
    UI state and what Kit's first-person navmesh bridge expects).
    """

    def __init__(self) -> None:
        self._walking_handle: Optional[Any] = None
        self._wheelchair_handle: Optional[Any] = None
        self._active_mode: str = "walking"
        self._orchestrator = None

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def attach_orchestrator(self, orchestrator) -> None:
        """Store a reference to the orchestrator (needed for per-mode agent settings)."""
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Active-mode state
    # ------------------------------------------------------------------

    def get_active_mode(self) -> str:
        return self._active_mode

    def set_active_mode(self, mode: str) -> bool:
        norm = (mode or "").strip().lower()
        if norm not in _VALID_MODES:
            print(f"[MODE_CACHE] Unknown mode '{mode}' — ignored")
            return False
        if norm == self._active_mode:
            return True
        self._active_mode = norm
        print(f"[MODE_CACHE] Active mode -> {norm}")
        return True

    def get_active_navmesh(self) -> Optional[Any]:
        """Return the cached handle for the currently-selected mode, or None."""
        if self._active_mode == "wheelchair":
            return self._wheelchair_handle
        return self._walking_handle

    def get_handles(self) -> tuple[Optional[Any], Optional[Any]]:
        """Return ``(walking_handle, wheelchair_handle)`` for dual-mesh consumers."""
        return (self._walking_handle, self._wheelchair_handle)

    def is_ready(self) -> bool:
        """True when both modes have been successfully baked at least once."""
        return self._walking_handle is not None and self._wheelchair_handle is not None

    # ------------------------------------------------------------------
    # Baking
    # ------------------------------------------------------------------

    async def _acquire_handle(self) -> Optional[Any]:
        """Read the currently-active NavMesh handle from Kit."""
        try:
            import omni.anim.navigation.core as nav_module

            inav = nav_module.acquire_interface()
            if not inav:
                return None
            return inav.get_navmesh()
        except Exception as exc:
            print(f"[MODE_CACHE] acquire handle failed: {exc}")
            return None

    async def _bake_mode_once(self, mode: str) -> Optional[Any]:
        """Single bake attempt for a mode; returns handle on success, None on failure."""
        if self._orchestrator is None:
            print("[MODE_CACHE] No orchestrator attached — cannot resolve agent settings")
            return None
        settings = self._orchestrator.get_agent_settings_for_mode(mode)
        if not settings:
            print(f"[MODE_CACHE] No agent settings for mode '{mode}'")
            return None
        ok = await _change_agent_settings_and_rebake(settings)
        if not ok:
            return None
        handle = await self._acquire_handle()
        if handle is None:
            print(f"[MODE_CACHE] Bake reported success but get_navmesh() returned None for '{mode}'")
        return handle

    async def _bake_mode_with_retries(self, mode: str) -> Optional[Any]:
        """Bake one mode up to _BAKE_RETRY_COUNT times; returns handle or None."""
        for attempt in range(1, _BAKE_RETRY_COUNT + 1):
            print(f"[MODE_CACHE] Baking '{mode}' (attempt {attempt}/{_BAKE_RETRY_COUNT})...")
            handle = await self._bake_mode_once(mode)
            if handle is not None:
                print(f"[MODE_CACHE] '{mode}' baked & cached (attempt {attempt})")
                return handle
            print(f"[MODE_CACHE] '{mode}' bake attempt {attempt} failed")
        return None

    async def bake_both_modes(self) -> bool:
        """Serial bake of both modes: wheelchair first, walking last.

        Walking is baked last so ``inav.get_navmesh()`` (the "active" mesh
        Kit's first-person bridge sees) matches the default UI state.

        On failure for either mode the previous handle (if any) is retained
        so routing can continue against the last-known-good mesh.

        Returns True only when BOTH modes successfully produced a handle
        at least once in this call; partial success returns False.
        """
        print("[MODE_CACHE] Dual-mode bake starting (wheelchair -> walking)")

        wc = await self._bake_mode_with_retries("wheelchair")
        if wc is not None:
            self._wheelchair_handle = wc

        # Yield a frame so is_navmesh_baking() definitely clears between bakes.
        try:
            await kit_app.get_app().next_update_async()
        except Exception:
            pass

        w = await self._bake_mode_with_retries("walking")
        if w is not None:
            self._walking_handle = w

        success = (wc is not None) and (w is not None)
        if success:
            print(
                f"[MODE_CACHE] Dual-mode bake complete — active='{self._active_mode}', "
                f"both handles cached"
            )
        else:
            print(
                f"[MODE_CACHE] Dual-mode bake INCOMPLETE — "
                f"walking_cached={self._walking_handle is not None}, "
                f"wheelchair_cached={self._wheelchair_handle is not None}"
            )
        return success
