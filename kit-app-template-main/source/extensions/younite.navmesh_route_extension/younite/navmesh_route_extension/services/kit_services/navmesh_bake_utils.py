"""
Shared NavMesh baking utilities.

Standalone async functions for ensuring NavMesh readiness, changing agent
settings, and triggering rebakes.  Used by both NavMeshRouteService (service-
level pre-bake) and RouteInstance (per-route initial wait).
"""
from __future__ import annotations

import time

_NAVMESH_BAKE_TIMEOUT_SEC = 30.0


async def wait_for_navmesh_ready(*, timeout_sec: float = _NAVMESH_BAKE_TIMEOUT_SEC, log_prefix: str = "NAVMESH") -> bool:
    """Ensure a baked NavMesh is available, triggering a bake if needed.

    All waits are predicate-driven with a wall-clock deadline.
    """
    try:
        import omni.kit.app as kit_app
        import omni.anim.navigation.core as nav_module

        inav = nav_module.acquire_interface()
        if not inav:
            print(f"[{log_prefix}] No navigation interface for pre-bake")
            return True

        deadline = time.monotonic() + timeout_sec

        if hasattr(inav, "is_navmesh_baking") and inav.is_navmesh_baking():
            print(f"[{log_prefix}] NavMesh bake already in progress, waiting...")
            while time.monotonic() < deadline:
                await kit_app.get_app().next_update_async()
                if not inav.is_navmesh_baking():
                    print(f"[{log_prefix}] NavMesh bake completed")
                    return True
            print(f"[{log_prefix}] NavMesh bake timed out (already-in-progress)")
            return False

        navmesh = inav.get_navmesh()
        if navmesh:
            return True

        print(f"[{log_prefix}] No baked NavMesh found — triggering auto-bake...")
        _trigger_bake(inav, log_prefix)

        for _ in range(10):
            await kit_app.get_app().next_update_async()

        frame = 0
        while time.monotonic() < deadline:
            await kit_app.get_app().next_update_async()
            is_baking = hasattr(inav, "is_navmesh_baking") and inav.is_navmesh_baking()
            if not is_baking:
                nm = inav.get_navmesh()
                if nm:
                    print(f"[{log_prefix}] NavMesh auto-bake completed successfully")
                    return True
                if frame < 30:
                    frame += 1
                    continue
                print(f"[{log_prefix}] Bake finished but no navmesh available")
                return False
            frame += 1
            if frame % 60 == 0:
                print(f"[{log_prefix}] Auto-bake in progress... ({frame / 60:.1f}s)")

        print(f"[{log_prefix}] Auto-bake timed out")
        return False
    except Exception as e:
        print(f"[{log_prefix}] wait_for_navmesh_ready exception: {e}")
        return True


def _trigger_bake(inav, log_prefix: str = "NAVMESH") -> None:
    """Call whichever bake API exists on the navigation interface."""
    try:
        if hasattr(inav, "start_navmesh_baking"):
            inav.start_navmesh_baking()
        elif hasattr(inav, "bake"):
            inav.bake()
        elif hasattr(inav, "bake_navmesh"):
            inav.bake_navmesh()
        else:
            print(f"[{log_prefix}] No bake API found on navigation interface")
    except Exception as e:
        print(f"[{log_prefix}] Bake trigger failed: {e}")


async def change_agent_settings_and_rebake(agent_settings: dict) -> bool:
    """Update navmesh agent settings via carb settings and in stage
    customLayerData (for persistence), then rebake.

    ``agent_settings`` maps setting names (e.g. "agentMaxStepHeight") to values.
    Returns True on success.
    """
    try:
        import carb.settings
        import omni.usd
        import omni.kit.app as kit_app
        import omni.anim.navigation.core as nav_module

        settings = carb.settings.get_settings()
        _CFG = "/exts/omni.anim.navigation.core/navMesh/config"

        for key, value in agent_settings.items():
            old_val = settings.get(f"{_CFG}/{key}")
            settings.set(f"{_CFG}/{key}", float(value))
            settings.set(f"/persistent{_CFG}/{key}", float(value))
            print(f"[NAVMESH_ROUTE] {key}: {old_val} -> {value} (carb settings)")

        ctx = omni.usd.get_context()
        stage = ctx.get_stage() if ctx else None
        if stage:
            try:
                root_layer = stage.GetRootLayer()
                custom_data = dict(root_layer.customLayerData)
                nav_settings = dict(custom_data.get("navmeshSettings", {}))
                for key, value in agent_settings.items():
                    nav_settings[key] = float(value)
                custom_data["navmeshSettings"] = nav_settings
                root_layer.customLayerData = custom_data
            except Exception as e:
                print(f"[NAVMESH_ROUTE] customLayerData update failed (non-fatal): {e}")

        inav = nav_module.acquire_interface()
        if not inav:
            print("[NAVMESH_ROUTE] No navigation interface for rebake")
            return False

        if hasattr(inav, "clear_cache_dir"):
            try:
                inav.clear_cache_dir()
            except Exception:
                pass

        _trigger_bake(inav, "NAVMESH_ROUTE")

        for _ in range(10):
            await kit_app.get_app().next_update_async()

        step_height = agent_settings.get("agentMaxStepHeight")
        for frame in range(600):
            await kit_app.get_app().next_update_async()
            is_baking = hasattr(inav, "is_navmesh_baking") and inav.is_navmesh_baking()
            if not is_baking:
                nm = inav.get_navmesh()
                if nm:
                    actual = nm.get_agent_max_step_height() if hasattr(nm, "get_agent_max_step_height") else "?"
                    print(f"[NAVMESH_ROUTE] Rebake completed (stepHeight requested={step_height}, baked={actual})")
                    return True
                if frame < 30:
                    continue
                print("[NAVMESH_ROUTE] Rebake finished but no navmesh available")
                return False
            if frame % 60 == 0 and frame > 0:
                print(f"[NAVMESH_ROUTE] Rebake in progress... ({frame / 60:.1f}s)")
        print("[NAVMESH_ROUTE] Rebake timed out")
        return False
    except Exception as e:
        print(f"[NAVMESH_ROUTE] change_agent_settings_and_rebake error: {e}")
        return False


async def rebake_navmesh() -> bool:
    """Trigger a NavMesh rebake without changing agent settings."""
    try:
        import omni.kit.app as kit_app
        import omni.anim.navigation.core as nav_module

        inav = nav_module.acquire_interface()
        if not inav:
            print("[NAVMESH_ROUTE] No navigation interface for rebake")
            return False

        if hasattr(inav, "clear_cache_dir"):
            try:
                inav.clear_cache_dir()
            except Exception:
                pass

        _trigger_bake(inav, "NAVMESH_ROUTE")

        for _ in range(10):
            await kit_app.get_app().next_update_async()

        for frame in range(600):
            await kit_app.get_app().next_update_async()
            is_baking = hasattr(inav, "is_navmesh_baking") and inav.is_navmesh_baking()
            if not is_baking:
                nm = inav.get_navmesh()
                if nm:
                    print("[NAVMESH_ROUTE] Rebake completed")
                    return True
                if frame < 30:
                    continue
                print("[NAVMESH_ROUTE] Rebake finished but no navmesh available")
                return False
            if frame % 60 == 0 and frame > 0:
                print(f"[NAVMESH_ROUTE] Rebake in progress... ({frame / 60:.1f}s)")
        print("[NAVMESH_ROUTE] Rebake timed out")
        return False
    except Exception as e:
        print(f"[NAVMESH_ROUTE] rebake_navmesh error: {e}")
        return False
