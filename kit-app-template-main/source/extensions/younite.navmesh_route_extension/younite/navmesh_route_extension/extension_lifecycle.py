"""Service wiring and teardown for `NavMeshRouteExtension` (keeps `extension.py` thin)."""

from __future__ import annotations

import asyncio


def startup_navmesh_route_services(ext) -> None:
    """Construct route services, orchestrator, bridge hooks, and FP navmesh prepare."""
    from .services.kit_services.navmesh_route_service import NavMeshRouteService
    from .services.kit_services.navmesh_bake_orchestrator import (
        NavMeshBakeOrchestrator,
        CameraAreaProvider,
        IncidentAreaProvider,
        SoundAreaProvider,
        CameraDepthObstacleProvider,
    )
    from .services.kit_services.navmesh_mode_cache import NavMeshModeCache
    from .navmesh_route_bridge import set_navmesh_route_dev_hooks
    from .services.kit_services.bird_eye_route_projector import BirdEyeRouteProjector
    from .services.kit_services.bird_eye_pin_service import BirdEyePinService
    from .services.kit_services.osm_route_overlay import OsmRouteOverlayService
    from .services.kit_services.route_composer import RouteComposer
    from .services.kit_services.shortcut_router import ShortcutRouter, set_shortcut_router
    from .services.kit_services.shortcut_traversal_service import ShortcutTraversalService

    ext._svc = NavMeshRouteService()
    ext._bird_eye_route = BirdEyeRouteProjector()
    ext._bird_eye_route.start()

    ext._mode_cache = NavMeshModeCache()
    ext._svc.set_mode_cache(ext._mode_cache)

    ext._route_composer = RouteComposer(mode_cache=ext._mode_cache)
    try:
        from .services.kit_services.route_composer import (
            set_route_composer,
            set_route_service,
        )

        set_route_composer(ext._route_composer)
        set_route_service(ext._svc)
    except Exception:
        pass

    ext._shortcut_router = ShortcutRouter()
    set_shortcut_router(ext._shortcut_router)
    ext._shortcut_traversal = ShortcutTraversalService(
        get_router=lambda: ext._shortcut_router,
        get_route_service=lambda: ext._svc,
    )
    ext._shortcut_traversal.start()

    ext._bird_eye_pin = BirdEyePinService(
        mode_cache=ext._mode_cache,
        route_projector=ext._bird_eye_route,
    )
    ext._bird_eye_pin.start()

    ext._osm_route_overlay = OsmRouteOverlayService(
        mode_cache=ext._mode_cache,
        navmesh_route_service=ext._svc,
    )
    ext._osm_route_overlay.start()

    overlay_svc = ext._osm_route_overlay

    def _player_compose_may_use_osm_bridge() -> bool:
        try:
            import carb

            if (
                str(carb.settings.get_settings().get("/younite/camera/viewType") or "")
                == "birdEye"
            ):
                return True
        except Exception:
            pass
        try:
            return bool(overlay_svc.is_overlay_visible())
        except Exception:
            return False

    ext._svc.set_player_osm_bridge_policy(_player_compose_may_use_osm_bridge)

    ext._camera_provider = CameraAreaProvider()
    ext._incident_provider = IncidentAreaProvider()
    ext._sound_provider = SoundAreaProvider()
    ext._camera_depth_provider = CameraDepthObstacleProvider()

    async def _orchestrator_dual_bake(*_args, **_kwargs) -> bool:
        ok = await ext._mode_cache.bake_both_modes()
        if ok:
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("navmeshDualBakeComplete", {"success": True})
            except Exception as exc:
                print(f"[navmesh_route] navmeshDualBakeComplete dispatch failed: {exc}")
        return ok

    ext._orchestrator = NavMeshBakeOrchestrator(
        do_rebake=_orchestrator_dual_bake,
        do_settings_rebake=_orchestrator_dual_bake,
        recalc_routes=ext._svc.recalc_all_routes,
    )
    ext._mode_cache.attach_orchestrator(ext._orchestrator)
    ext._orchestrator.register_provider(ext._camera_provider)
    ext._orchestrator.register_provider(ext._incident_provider)
    ext._orchestrator.register_provider(ext._sound_provider)
    ext._orchestrator.register_provider(ext._camera_depth_provider)

    def _schedule_rebake_if_idle() -> None:
        try:
            if ext._initial_bake_task is None or ext._initial_bake_task.done():
                ext._initial_bake_task = asyncio.ensure_future(ext._orchestrator.request_rebake())
        except Exception as exc:
            print(f"[navmesh_route] schedule rebake if idle failed: {exc}")

    set_navmesh_route_dev_hooks(ext._mode_cache, _schedule_rebake_if_idle)

    try:
        from younite.usd_viewer_stage_core_extension.first_person_navmesh_bridge import (
            set_first_person_navmesh_prepare,
        )

        async def _ensure_dual_mode_ready() -> bool:
            if ext._mode_cache.is_ready():
                return True
            task = ext._initial_bake_task
            if task is not None and not task.done():
                try:
                    await task
                except Exception:
                    pass
                return ext._mode_cache.is_ready()
            return await ext._orchestrator.request_rebake()

        set_first_person_navmesh_prepare(_ensure_dual_mode_ready)
    except Exception as e:
        print(f"[navmesh_route] first-person navmesh bridge registration failed: {e}")


def shutdown_navmesh_route_services(ext) -> None:
    try:
        from .navmesh_route_bridge import clear_navmesh_route_dev_hooks

        clear_navmesh_route_dev_hooks()
    except Exception:
        pass
    try:
        from younite.usd_viewer_stage_core_extension.first_person_navmesh_bridge import (
            set_first_person_navmesh_prepare,
        )

        set_first_person_navmesh_prepare(None)
    except Exception:
        pass
    try:
        from .services.kit_services.route_composer import (
            set_route_composer,
            set_route_service,
        )

        set_route_composer(None)
        set_route_service(None)
    except Exception:
        pass
    try:
        from .services.kit_services.shortcut_router import set_shortcut_router

        set_shortcut_router(None)
    except Exception:
        pass
    try:
        if getattr(ext, "_shortcut_traversal", None):
            ext._shortcut_traversal.stop()
    except Exception:
        pass
    ext._shortcut_traversal = None
    ext._shortcut_router = None
    try:
        from .services.kit_services.seat_lookup import reload as reload_seats

        reload_seats()
    except Exception:
        pass
    cam = getattr(ext, "_camera_provider", None)
    if cam and cam.is_active():
        try:
            cam.remove_areas()
        except Exception:
            pass
    snd = getattr(ext, "_sound_provider", None)
    if snd and snd.is_active():
        try:
            snd.remove_areas()
        except Exception:
            pass
    cdp = getattr(ext, "_camera_depth_provider", None)
    if cdp and cdp.is_active():
        try:
            cdp.remove_areas()
        except Exception:
            pass
    try:
        if getattr(ext, "_bird_eye_route", None):
            ext._bird_eye_route.shutdown()
    except Exception:
        pass
    ext._bird_eye_route = None
    try:
        if getattr(ext, "_bird_eye_pin", None):
            ext._bird_eye_pin.stop()
    except Exception:
        pass
    ext._bird_eye_pin = None
    try:
        if getattr(ext, "_osm_route_overlay", None):
            ext._osm_route_overlay.stop()
    except Exception:
        pass
    ext._osm_route_overlay = None
    try:
        if getattr(ext, "_svc", None):
            ext._svc.stop_route_calculation()
    except Exception:
        pass
    ext._subs.clear()
    ext._svc = None
    ext._orchestrator = None
    ext._mode_cache = None
