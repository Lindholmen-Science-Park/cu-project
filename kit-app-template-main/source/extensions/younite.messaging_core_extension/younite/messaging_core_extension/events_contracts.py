"""
Event name + payload contract constants.

This used to live in a standalone events-contracts extension, but it's just constants,
so keeping it as a plain module inside MessagingCore reduces extension count.
"""


class Events:
    # ---- Scene lifecycle ----
    SCENE_LOADING = "scene.loading"
    SCENE_LOADED = "scene.loaded"

    # ---- Picking (shared) ----
    PICK_REQUEST = "younite.pick.request"
    PICK_RESULT = "younite.pick.result"

    # ---- Dev OSM route overlay (navmesh_route_extension) ----
    OSM_ROUTE_OVERLAY_SET = "osmRouteOverlaySet"
    OSM_ROUTE_OVERLAY_STATUS = "osmRouteOverlayStatus"

    # ---- Stage readiness ----
    STAGE_READY = "stageReady"
    STAGE_CLOSED = "stageClosed"

    # ---- Player readiness ----
    PLAYER_READY = "younite.player.ready"

