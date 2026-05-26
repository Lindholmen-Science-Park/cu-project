"""NavMesh bake orchestrator — single entry-point for rebakes."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict, List, Optional

from .agent_defaults import read_walking_agent_defaults_from_stage
from .area_registration import sync_provider_areas_to_custom_layer
from .constants import WHEELCHAIR_AGENT_SETTINGS
from .diagnostics import log_baked_navmesh_areas as _emit_baked_area_diag
from .lod import ensure_full_lod_for_bake, restore_lod
from .protocol import NavMeshAreaProvider


class NavMeshBakeOrchestrator:
    """Single entry-point for all NavMesh rebakes.

    * Maintains a registry of ``NavMeshAreaProvider`` instances.
    * Before every bake, calls ``prepare_for_bake()`` on each *active*
      provider so its area prims are present for the baker.
    * After every bake, calls ``after_bake()`` on each *active* provider
      (e.g. to hide debug visuals).
    * Serialises concurrent rebake requests with an ``asyncio.Lock``.
    """

    def __init__(
        self,
        do_rebake: Callable[[], Awaitable[bool]],
        do_settings_rebake: Callable[[dict], Awaitable[bool]],
        recalc_routes: Callable[[], None],
    ):
        self._do_rebake = do_rebake
        self._do_settings_rebake = do_settings_rebake
        self._recalc_routes = recalc_routes
        self._providers: Dict[str, NavMeshAreaProvider] = {}
        self._bake_lock = asyncio.Lock()
        self._scene_agent_defaults: Dict[str, float] = {}

    # -- Provider registry --------------------------------------------------

    def register_provider(self, provider: NavMeshAreaProvider) -> None:
        self._providers[provider.name] = provider
        print(f"[BAKE_ORCH] Registered provider '{provider.name}'")

    def unregister_provider(self, name: str) -> None:
        removed = self._providers.pop(name, None)
        if removed:
            print(f"[BAKE_ORCH] Unregistered provider '{name}'")

    def get_provider(self, name: str) -> Optional[NavMeshAreaProvider]:
        return self._providers.get(name)

    # -- Agent defaults -----------------------------------------------------

    def read_scene_agent_defaults(self) -> None:
        """Read walking-mode agent settings from ``customLayerData`` (once per bake)."""
        defaults = read_walking_agent_defaults_from_stage()
        if defaults:
            self._scene_agent_defaults = defaults
            print(f"[BAKE_ORCH] Walking defaults from scene: {defaults}")
        else:
            print("[BAKE_ORCH] ⚠ No agent settings found in customLayerData")

    def get_agent_settings_for_mode(self, mode: str) -> Optional[Dict[str, float]]:
        """``walking`` → scene USD defaults; ``wheelchair`` → explicit preset."""
        mode = mode.strip().lower()
        if mode == "walking":
            if not self._scene_agent_defaults:
                self.read_scene_agent_defaults()
            return dict(self._scene_agent_defaults)
        if mode == "wheelchair":
            return dict(WHEELCHAIR_AGENT_SETTINGS)
        return None

    # -- Area registration ---------------------------------------------------

    def ensure_areas_registered(self) -> None:
        """Ensure provider area defs exist in ``customLayerData`` (warn + merge)."""
        if not self._scene_agent_defaults:
            self.read_scene_agent_defaults()

        sync_provider_areas_to_custom_layer(self._providers)

    # -- Rebake -------------------------------------------------------------

    async def request_rebake(
        self, *, agent_settings: Optional[Dict[str, float]] = None
    ) -> bool:
        """Serialised rebake: providers → bake → diagnostics → after_bake → recalc routes."""
        async with self._bake_lock:
            self.ensure_areas_registered()

            lod_to_restore = await ensure_full_lod_for_bake()

            try:
                active_names: List[str] = []

                for provider in self._providers.values():
                    if provider.is_active():
                        active_names.append(provider.name)
                        try:
                            provider.prepare_for_bake()
                        except Exception as exc:
                            print(
                                f"[BAKE_ORCH] prepare_for_bake failed for '{provider.name}': {exc}"
                            )

                settings_summary = (
                    f", settings={agent_settings}" if agent_settings else ""
                )
                print(
                    f"[BAKE_ORCH] Rebaking (active providers: {active_names or 'none'}{settings_summary})"
                )

                if agent_settings:
                    ok = await self._do_settings_rebake(agent_settings)
                else:
                    ok = await self._do_rebake()

                _emit_baked_area_diag()

                for provider in self._providers.values():
                    if provider.is_active():
                        try:
                            provider.after_bake()
                        except Exception as exc:
                            print(
                                f"[BAKE_ORCH] after_bake failed for '{provider.name}': {exc}"
                            )

                try:
                    self._recalc_routes()
                except Exception as exc:
                    print(f"[BAKE_ORCH] recalc_routes failed: {exc}")

                return ok
            finally:
                if lod_to_restore:
                    await restore_lod(lod_to_restore)
