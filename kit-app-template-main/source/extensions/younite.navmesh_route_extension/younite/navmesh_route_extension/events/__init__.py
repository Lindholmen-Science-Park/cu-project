"""Subscribe carb Events 2.0 handlers for `NavMeshRouteExtension`."""

from __future__ import annotations


def register_navmesh_route_events(ext) -> None:
    """
    Register outbound event names and observe inbound routing / UX events.

    POI data is loaded **before** route handlers so ``navmeshRouteCalculate``
    always sees a populated ``waypoint_route_ids`` set (fixes a latent
    startup race vs the monolithic extension ordering).
    """
    try:
        from younite.messaging_core_extension.message_utils import (
            normalize_event_payload,
            register_outbound_events,
        )

        register_outbound_events([
            "seatNavigateResult",
            "seatTeleportResult",
            "seatLayoutChanged",
            "poiTeleportResult",
            "geoTeleportResult",
            "navmeshRouteError",
            "navmeshRouteReady",
            "birdEyeRouteOverlay",
            "shortcutTraversalBegin",
            "shortcutTraversalComplete",
            "shortcutTraversalError",
            "shortcutsStatus",
            "shortcutsPreferStatus",
        ])

        import carb
        import carb.eventdispatcher
        import omni.kit.app as kit_app

        ed = carb.eventdispatcher.get_eventdispatcher()

        from .poi_state import load_poi_state
        from .wiring import NavmeshWireContext, make_observe, make_view_transition_dispatchers

        observe = make_observe(ext, ed)
        dispatch_ready, dispatch_ready_after_settle = make_view_transition_dispatchers(ed)

        ctx = NavmeshWireContext(
            ext=ext,
            ed=ed,
            carb=carb,
            kit_app=kit_app,
            observe=observe,
            normalize_event_payload=normalize_event_payload,
        )
        load_poi_state(ctx)

        from .routes_and_areas import register as register_routes_and_areas
        from .seat_navigation import register as register_seat_navigation
        from .poi_routes import register as register_poi_routes
        from .bird_eye_routes import register as register_bird_eye_routes
        from .geo_and_shortcuts import register as register_geo_and_shortcuts

        register_routes_and_areas(ctx)
        register_seat_navigation(ctx, dispatch_ready, dispatch_ready_after_settle)
        register_poi_routes(ctx, dispatch_ready, dispatch_ready_after_settle)
        register_bird_eye_routes(ctx)
        register_geo_and_shortcuts(ctx, dispatch_ready, dispatch_ready_after_settle)

    except Exception as e:
        print(f"[navmesh_route] subscribe failed: {e}")
