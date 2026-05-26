"""
WGS84 (lat/lon) → USD scene position for player teleport.

Phase 0 / Chrome "Explore in 3D" pipeline:
- When GeoCoordinateService is ready (CesiumGeoreference + tileset alignment on stage),
  uses the same ENU math as geo_coordinate_service.py.
- When not ready, returns a fixed stub position so end-to-end messaging can be tested
  without silently failing (PlayerSpawnPoint_01 world translate — see player_spawnpoints_layer.usda).

Ellipsoid / georeference height rarely matches authored mesh ground. After lat/lon → (x,y,z),
we gather PhysX + tight + loose NavMesh Y candidates, drop implausible lows (tunnels), pick the
closest to reference ground height, else fall back to max(raw, default spawn Y); then a small lift.
"""

from __future__ import annotations

from typing import Final, Optional, Tuple

from .geo_coordinate_service import get_geo_coordinate_service

# PlayerSpawnPoint_01 xformOp:translate (cm) — source/data/scenes/sublayers/player_spawnpoints_layer.usda
_STUB_PLAYER_SPAWN_01_XYZ: Final[Tuple[float, float, float]] = (
    -5778.041302571314,
    2245.785888627629,
    -5907.339475028431,
)

# Ray from high above (cm) — scene metersPerUnit typically 0.01
_RAY_START_Y_CM: Final[float] = 120_000.0  # 1200 m
_RAY_MAX_DIST_CM: Final[float] = 150_000.0
# Raise snapped Y slightly — hit surface is often mesh floor; player pivot needs clearance (cm).
_GEO_SNAP_Y_LIFT_CM: Final[float] = 85.0
# Reject snap hits far below normal exterior walkable height (avoids tunnel / basement navmesh islands).
_REASONABLE_Y_MIN_CM: Final[float] = 600.0


def _navmesh_ground_y_near_height(x: float, y_center: float, z: float, half_height_cm: float) -> Optional[float]:
    """NavMesh nearest point with a tight vertical window around an expected ground height."""
    try:
        import omni.anim.navigation.core as nav_module
        import carb

        inav = nav_module.acquire_interface()
        if not inav:
            return None
        navmesh = inav.get_navmesh()
        if not navmesh or not hasattr(navmesh, "find_nearest_point"):
            return None

        pt = carb.Float3(float(x), float(y_center), float(z))
        extent = carb.Float3(2500.0, float(half_height_cm), 2500.0)
        nearest = navmesh.find_nearest_point(pt, extent)
        if nearest is None:
            return None
        try:
            return float(nearest.y) if hasattr(nearest, "y") else float(nearest[1])
        except Exception:
            return None
    except Exception:
        return None


def _navmesh_ground_y_large_extent(x: float, y: float, z: float) -> Optional[float]:
    """NavMesh closest walkable point with tall vertical extent (raw geo Y can be far off)."""
    try:
        import omni.anim.navigation.core as nav_module
        import carb

        inav = nav_module.acquire_interface()
        if not inav:
            return None
        navmesh = inav.get_navmesh()
        if not navmesh or not hasattr(navmesh, "find_nearest_point"):
            return None

        pt = carb.Float3(float(x), float(y), float(z))
        # Half-extents (cm): wide XZ, very tall Y so underground / sky points still resolve.
        extent = carb.Float3(2500.0, 50_000.0, 2500.0)
        nearest = navmesh.find_nearest_point(pt, extent)
        if nearest is None:
            return None
        try:
            return float(nearest.y) if hasattr(nearest, "y") else float(nearest[1])
        except Exception:
            return None
    except Exception:
        return None


def _hit_prim_path_lower(hit) -> str:
    if not isinstance(hit, dict):
        return ""
    for k in ("colliderPrimPath", "bodyPrimPath", "primPath", "path"):
        v = hit.get(k)
        if isinstance(v, str):
            return v.lower()
    return ""



def _physx_ground_y_from_above(x: float, z: float, player_path: str) -> Optional[float]:
    """Shoot downward from high Y; skip player capsule and Cesium tile colliders (often below city mesh)."""
    try:
        import omni.physx
        import carb._carb as _carb_c

        sqi = omni.physx.get_physx_scene_query_interface()
        if not sqi:
            return None

        origin = _carb_c.Float3(float(x), float(_RAY_START_Y_CM), float(z))
        direction = _carb_c.Float3(0.0, -1.0, 0.0)
        hit = sqi.raycast_closest(origin, direction, float(_RAY_MAX_DIST_CM), True)
        if not hit or not hit.get("hit", False):
            return None

        path_l = _hit_prim_path_lower(hit)
        if player_path.lower() in path_l:
            return None
        if "cesium" in path_l:
            return None

        hit_pos = hit.get("position")
        if hit_pos is None:
            return None
        if hasattr(hit_pos, "__getitem__") and len(hit_pos) >= 2:
            return float(hit_pos[1])
        return None
    except Exception:
        return None


def snap_geo_scene_position_to_ground(
    x: float, y: float, z: float, *, quiet: bool = False
) -> Tuple[float, float, float]:
    """
    Return (x, y_snapped, z) at walkable / collider ground under (x, z).

    Collects PhysX + NavMesh candidates, drops hits with Y far below plausible exterior ground
    (large navmesh search often snaps to tunnels / basements, e.g. Y ~ -3500 cm).
    Picks the candidate closest to max(raw_ellipsoid_y, default_spawn_y); otherwise falls back
    to that reference height at this XZ.

    Set ``quiet=True`` when snapping many markers (e.g. transit overlay) to avoid log spam.
    """
    from .world_conventions import PLAYER_CHARACTER_PATH

    player_path = str(PLAYER_CHARACTER_PATH)
    ref_y = float(_STUB_PLAYER_SPAWN_01_XYZ[1])
    y_raw = float(y)

    def _apply_lift(y_hit: float, source: str) -> Tuple[float, float, float]:
        y_out = float(y_hit) + float(_GEO_SNAP_Y_LIFT_CM)
        if not quiet and abs(y_raw - y_out) > 5.0:
            print(
                f"[geo_teleport_transform] ground snap ({source}): Y {y_raw:.1f} → {y_out:.1f} "
                f"at XZ ({x:.1f}, {z:.1f})"
            )
        return (float(x), y_out, float(z))

    candidates: list[tuple[str, float]] = []

    y_px = _physx_ground_y_from_above(x, z, player_path)
    if y_px is not None and y_px >= float(_REASONABLE_Y_MIN_CM):
        candidates.append(("physx", float(y_px)))

    # Tight vertical search around typical ground (street level), not global nearest in ±500 m Y.
    y_probe = max(y_raw, ref_y - 300.0, float(_REASONABLE_Y_MIN_CM) + 200.0)
    y_nm_tight = _navmesh_ground_y_near_height(x, y_probe, z, half_height_cm=2500.0)
    if y_nm_tight is not None and y_nm_tight >= float(_REASONABLE_Y_MIN_CM):
        candidates.append(("navmesh_tight", float(y_nm_tight)))

    y_nm_loose = _navmesh_ground_y_large_extent(x, y_raw, z)
    if y_nm_loose is not None and y_nm_loose >= float(_REASONABLE_Y_MIN_CM):
        candidates.append(("navmesh_loose", float(y_nm_loose)))

    target_y = max(y_raw, ref_y)

    if candidates:
        source, y_best = min(candidates, key=lambda t: abs(t[1] - target_y))
        if not quiet:
            print(
                f"[geo_teleport_transform] ground snap chose {source} among {len(candidates)} "
                f"candidate(s); y_hit={y_best:.1f} (target≈{target_y:.1f})"
            )
        return _apply_lift(y_best, source)

    y_fb = max(y_raw, ref_y)
    if not quiet:
        print(
            f"[geo_teleport_transform] no reasonable physx/navmesh Y (min={_REASONABLE_Y_MIN_CM} cm) — "
            f"fallback Y={y_fb:.1f} from max(raw={y_raw:.1f}, ref_spawn_y={ref_y:.1f}) at XZ ({x:.1f}, {z:.1f})"
        )
    return _apply_lift(y_fb, "fallback_max_raw_or_ref")


def latlon_to_scene_xyz_for_teleport(
    lat: float,
    lon: float,
    height_m: float = 0.0,
    *,
    snap_to_ground: bool = True,
) -> Tuple[float, float, float]:
    """
    Resolve (latitude, longitude, optional WGS84 height in metres) to scene (x, y, z).

    When georef is ready and ``snap_to_ground`` is True, Y is adjusted to NavMesh / collider
    under the horizontal position so ellipsoid height mismatches do not bury the player.

    Returns stub spawn when GeoCoordinateService is unavailable or not yet loaded from stage.
    """
    geo = get_geo_coordinate_service()
    if geo is not None and geo.ready:
        out = geo.latlon_to_usd(lat, lon, height_m)
        if out is not None:
            x, y, z = float(out[0]), float(out[1]), float(out[2])
            print(
                f"[geo_teleport_transform] lat/lon→USD raw (scene cm, before ground snap): "
                f"lat={lat:.6f} lon={lon:.6f} h_m={height_m} → ({x:.2f}, {y:.2f}, {z:.2f})"
            )
            if snap_to_ground:
                fx, fy, fz = snap_geo_scene_position_to_ground(x, y, z, quiet=False)
                print(
                    f"[geo_teleport_transform] after ground snap (scene cm, teleport target): "
                    f"({fx:.2f}, {fy:.2f}, {fz:.2f})"
                )
                return (fx, fy, fz)
            return (x, y, z)
    sx, sy, sz = _STUB_PLAYER_SPAWN_01_XYZ
    print(
        "[geo_teleport_transform] georef not ready — stub spawn (scene cm): "
        f"lat={lat:.6f} lon={lon:.6f} → ({sx:.2f}, {sy:.2f}, {sz:.2f})"
    )
    return _STUB_PLAYER_SPAWN_01_XYZ
