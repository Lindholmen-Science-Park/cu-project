"""Tunables and interval constants for the route engine."""

# Safety cap: abandon wait for player pathfind after this many seconds.
PLAYER_PATH_CALC_TIMEOUT_SEC = 1.0

# Between full recalcs, emit lightweight remaining-distance updates at this interval.
LIGHTWEIGHT_MEASURE_INTERVAL_SEC = 0.5

# seat_nav + auto_move: log once when remaining polyline length drops below this (route
# continues until auto-mover / snap completes).
ROUTE_ARRIVAL_THRESHOLD_CM = 100.0
# Along-polyline remaining distance must be <= this for AABB arrival to count (cm), so a
# teleported overlap with the destination volume far from the active route does not fire.
ARRIVAL_PATH_GUARD_MAX_REMAINING_CM = 1200.0
# World-space axis-aligned box at the polyline endpoint (stage units = cm). Half-extents
# from the last vertex; inclusion test is min/max only (no PhysX, no per-frame USD bounds).
ARRIVAL_AABB_HALF_XZ_CM = 100.0
ARRIVAL_AABB_HALF_Y_CM = 160.0
# seat_nav manual walk: wider horizontal box so CU celebration can fire in the aisle.
ARRIVAL_SEAT_MANUAL_AABB_HALF_XZ_CM = 180.0
ARRIVAL_SEAT_MANUAL_AABB_HALF_Y_CM = 160.0

# Master switch for the validated XZ straightening stage on calculated /
# guided routes (``seat_nav`` / ``find_my_seat`` / ``find_toilets`` /
# ``quiet_zone_nav`` / ``poi_nav`` / ``default``, single- or multi-leg).
# Player point-and-click is *unaffected* by this flag — that route lives
# in ``_player_compute_in_thread`` and always straightens.
#
# False (default) — straightening is OFF for every calculated route.
#   ``_straighten_path``'s XZ-only snap validation can accept a chord
#   that crosses a low wall when the NavMesh detour around it is short
#   (<10% longer than the chord) and the nearest NavMesh point at each
#   interior probe sits on the aisle/tier on the other side of the
#   wall — the rendered polyline then clips through the wall. Most
#   visible on ``seat_nav``'s final near-seat leg, after
#   ``_prune_passed_via_points`` (or ``plan_route``'s start-side
#   shortcut) has emptied the corridor list.
#
# True — restores the legacy behaviour:
#   * single-leg routes (``via_points`` empty) → straightening ON
#   * multi-leg corridor routes (``via_points`` set) → straightening
#     OFF (the composer's per-leg context still hard-codes False inside
#     ``_build_multi_segment_navmesh_route`` for the same wall-clip
#     reasons + O(n²) sub-query cost).
#
# Flip this to True if a future ``_straighten_path`` rework lifts the
# wall-clip hazard (e.g. by adding 3D-distance / Y-coherence to the
# snap validation, or by sampling the chord at finer intervals — see
# the discussion in the topic file ``navmesh-path-refinement.mdc``).
ENABLE_VALIDATED_STRAIGHTEN_CALCULATED_ROUTES = False
