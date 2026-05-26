#!/usr/bin/env python3
"""
Bake terrain-following OSM curves: regenerate ``gothenburg_roads.usda`` and
``gothenburg_graph.json`` with Y from PhysX raycasts against terrain meshes.
Processes every way in ``osm_cache.json`` (highways + railway from the current
``generate_roads`` Overpass union).

**Preferred run** (correct cwd + build): ``source\\data\\osm\\bake_roads.bat``
from repo root ``kit-app-template-main`` — the batch file ``pushd``s to root,
runs ``repo.bat build``, then launches Kit with ``--exec`` to this script.

Manual ``repo.bat launch`` with ``--exec`` must use **cwd = kit-app-template-main**
(see ``bake_roads.bat`` for the full Kit flags and exec path).

Flow:
  1. Open main scene (``YOUNITE_SCENE_NAME`` or ``main_scene.usda``)
  2. Apply PhysicsCollisionAPI to terrain mesh prims (session layer, temporary)
  3. Disable non-terrain colliders so raycasts hit ground only
  4. Start physics, wait for scene queries
  5. Read Cesium transform, load ``osm_cache.json``, convert node coords
  6. Raycast each node (multi-pass), spike filter, subdivide segments, write USDA + graph JSON
  7. ``post_quit()`` — Kit exits when done
"""

import asyncio
import json
import math
import os
import sys
from pathlib import Path

_TAG = "[BakeRoads]"

def _log(msg):
    print(f"{_TAG} {msg}", flush=True)

# ---------------------------------------------------------------------------
# Import generate_roads helpers (coord conversion, fetch, categorise, styles)
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent.resolve()
_OSM_DIR = _SCRIPT_DIR
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent.parent  # kit-app-template-main/

sys.path.insert(0, str(_OSM_DIR))
from generate_roads import (
    ROAD_STYLES,
    _WGS84_A,
    _WGS84_B,
    _WGS84_E2,
    _lat_lon_to_ecef,
    _ecef_to_usd,
    categorise,
    class_of,
    wheelchair_access,
    fetch,
    _distance_cm,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUBDIVIDE_MAX_CM = 1000.0   # max 10 m between points
ROAD_HOVER_CM = 50.0        # small hover above terrain to prevent z-fighting
RAYCAST_START_Y = 100000.0  # start ray from 1 km up (world-space, large scene)
RAYCAST_MAX_DIST = 200000.0
TERRAIN_PRIM_SUFFIX = "_Terrain"
GEOMETRY_CONTAINER = "/World/CU_DT_8km2_Project_Scene/Geometry"


# ---------------------------------------------------------------------------
# Terrain collider application (session layer)
# ---------------------------------------------------------------------------

async def _apply_terrain_colliders(stage, app):
    """Apply PhysicsCollisionAPI to all Mesh prims under *_Terrain Xforms.

    Applies in batches to avoid overwhelming PhysX GPU cooking.
    """
    from pxr import Usd, Sdf, UsdGeom, UsdPhysics

    session = stage.GetSessionLayer()
    count = 0
    BATCH_SIZE = 50

    with Usd.EditContext(stage, session):
        container = stage.GetPrimAtPath(GEOMETRY_CONTAINER)
        if not container or not container.IsValid():
            print(f"{_TAG} WARNING: {GEOMETRY_CONTAINER} not found, "
                  "trying full stage traversal")
            prims_to_check = list(stage.Traverse())
        else:
            prims_to_check = list(Usd.PrimRange(container))

        terrain_xforms = []
        for prim in prims_to_check:
            name = prim.GetName()
            if not name.endswith(TERRAIN_PRIM_SUFFIX):
                continue
            if not prim.IsA(UsdGeom.Xform) and not prim.IsA(UsdGeom.Scope):
                continue
            terrain_xforms.append(prim)

        _log(f"Found {len(terrain_xforms)} terrain Xforms")

        meshes = []
        for terrain_prim in terrain_xforms:
            for child in Usd.PrimRange(terrain_prim):
                if child.IsA(UsdGeom.Mesh):
                    meshes.append(child)

        _log(f"Applying collision to {len(meshes)} meshes "
             f"in batches of {BATCH_SIZE} ...")

        for i in range(0, len(meshes), BATCH_SIZE):
            batch = meshes[i:i + BATCH_SIZE]
            for child in batch:
                if not child.HasAPI(UsdPhysics.CollisionAPI):
                    UsdPhysics.CollisionAPI.Apply(child)
                approx = child.GetAttribute("physics:approximation")
                if not approx or not approx.IsValid():
                    child.CreateAttribute(
                        "physics:approximation", Sdf.ValueTypeNames.Token
                    ).Set("none")
                else:
                    approx.Set("none")
                enabled = child.GetAttribute("physics:collisionEnabled")
                if not enabled or not enabled.IsValid():
                    child.CreateAttribute(
                        "physics:collisionEnabled", Sdf.ValueTypeNames.Bool
                    ).Set(True)
                else:
                    enabled.Set(True)
                count += 1

            # Let PhysX breathe between batches
            for _ in range(5):
                await app.next_update_async()

    _log(f"Applied collision to {count} terrain mesh prims on session layer")
    return count


async def _disable_non_terrain_colliders(stage, app):
    """Disable collision on any existing non-terrain prims (e.g. arena walls).

    Prevents arena/building colliders from interfering with road raycasts.
    """
    from pxr import Usd, Sdf, UsdPhysics

    session = stage.GetSessionLayer()
    disabled = 0

    with Usd.EditContext(stage, session):
        for prim in stage.Traverse():
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            path_str = str(prim.GetPath())
            if "Terrain" in path_str:
                continue
            enabled = prim.GetAttribute("physics:collisionEnabled")
            if not enabled or not enabled.IsValid():
                prim.CreateAttribute(
                    "physics:collisionEnabled", Sdf.ValueTypeNames.Bool
                ).Set(False)
            else:
                enabled.Set(False)
            disabled += 1

    _log(f"Disabled {disabled} non-terrain colliders (arena/buildings)")
    for _ in range(5):
        await app.next_update_async()
    return disabled


# ---------------------------------------------------------------------------
# Raycasting
# ---------------------------------------------------------------------------

_sqi = None
_raycast_stats = {"hits": 0, "multi": 0, "lowest_chosen": 0}

def _get_sqi():
    global _sqi
    if _sqi is None:
        import omni.physx
        _sqi = omni.physx.get_physx_scene_query_interface()
    return _sqi


def _extract_terrain_y(hit) -> float | None:
    """Extract Y from a single hit dict if the prim path contains 'Terrain'."""
    prim_path = str(hit.get("rigidBody", "") or hit.get("collision", "") or "")
    if "Terrain" not in prim_path:
        return None
    pos = hit.get("position")
    if pos is not None and hasattr(pos, "__getitem__") and len(pos) >= 2:
        return float(pos[1])
    return None


def _terrain_y(x: float, z: float) -> float | None:
    """Raycast down and return the LOWEST terrain surface Y.

    Fires multiple passes of raycast_closest, each starting just below the
    previous hit, to penetrate through bridges/overpasses and find the
    actual ground surface underneath.
    """
    import carb._carb as _carb_c

    sqi = _get_sqi()
    if not sqi:
        return None

    direction = _carb_c.Float3(0.0, -1.0, 0.0)
    terrain_ys: list[float] = []
    ray_y = RAYCAST_START_Y

    for _ in range(5):
        origin = _carb_c.Float3(float(x), ray_y, float(z))
        hit = sqi.raycast_closest(origin, direction, RAYCAST_MAX_DIST, True)
        if not hit or not hit.get("hit", False):
            break
        pos = hit.get("position")
        if pos is None or not hasattr(pos, "__getitem__") or len(pos) < 2:
            break
        hit_y = float(pos[1])
        y = _extract_terrain_y(hit)
        if y is not None:
            terrain_ys.append(y)
        ray_y = hit_y - 100.0
        if ray_y < -100000.0:
            break

    if not terrain_ys:
        return None

    _raycast_stats["hits"] += 1
    if len(terrain_ys) > 1:
        _raycast_stats["multi"] += 1
        best = min(terrain_ys)
        if max(terrain_ys) - best > 100:
            _raycast_stats["lowest_chosen"] += 1
        return best
    return terrain_ys[0]


# ---------------------------------------------------------------------------
# Subdivision
# ---------------------------------------------------------------------------

def _subdivide_segment(ax, az, bx, bz):
    """Yield intermediate (x, z) points between a and b (excluding a)."""
    dx, dz = bx - ax, bz - az
    seg_len = math.hypot(dx, dz)
    if seg_len <= SUBDIVIDE_MAX_CM:
        yield (bx, bz)
        return
    steps = int(math.ceil(seg_len / SUBDIVIDE_MAX_CM))
    for s in range(1, steps):
        t = s / steps
        yield (ax + dx * t, az + dz * t)
    yield (bx, bz)


# ---------------------------------------------------------------------------
# Main async pipeline
# ---------------------------------------------------------------------------

async def _bake():
    import omni.usd
    import omni.kit.app

    app = omni.kit.app.get_app()

    # ---- 1. Open scene ----
    await app.next_update_async()
    usd_context = omni.usd.get_context()

    scene_name = os.environ.get("YOUNITE_SCENE_NAME", "").strip()
    if scene_name:
        if not scene_name.lower().endswith(".usda"):
            scene_name = f"{scene_name}.usda"
    else:
        scene_name = "main_scene.usda"

    scene_path = (_PROJECT_ROOT / "source" / "data" / "scenes" / scene_name).resolve()
    if not scene_path.exists():
        print(f"{_TAG} ERROR: Scene not found: {scene_path}")
        return

    _log(f"Opening scene: {scene_path.name} ...")
    await asyncio.sleep(1.0)
    result, error = await usd_context.open_stage_async(
        str(scene_path),
        load_set=omni.usd.UsdContextInitialLoadSet.LOAD_ALL,
    )
    if error:
        print(f"{_TAG} ERROR: Failed to open stage: {error}")
        return
    _log("Scene opened successfully")

    # Wait for assets to settle
    _log("Waiting for assets to load ...")
    for _ in range(120):
        await app.next_update_async()

    stage = usd_context.get_stage()
    if not stage:
        print(f"{_TAG} ERROR: No stage after open")
        return

    # ---- 2. Apply terrain colliders (session layer) ----
    _log("Applying terrain colliders ...")
    n_colliders = await _apply_terrain_colliders(stage, app)
    if n_colliders == 0:
        print(f"{_TAG} WARNING: No terrain meshes found — raycasts may miss")

    # Disable non-terrain colliders so raycasts only hit terrain surfaces
    await _disable_non_terrain_colliders(stage, app)

    # Disable livestream capture to speed up frame processing
    import carb.settings
    _settings = carb.settings.get_settings()
    _settings.set("/app/livestream/enabled", False)
    _settings.set("/app/livestream/skipEncoding", True)

    # Start physics simulation (required for scene queries)
    _log("Starting physics simulation ...")
    import omni.timeline
    timeline = omni.timeline.get_timeline_interface()
    timeline.play()

    # Poll until PhysX scene queries work (up to 60 frames)
    _log("Waiting for PhysX to become ready (polling) ...")
    physx_ready = False
    for attempt in range(60):
        await app.next_update_async()
        try:
            test_hit = _terrain_y(0.0, 0.0)
            if test_hit is not None:
                _log(f"PhysX ready after {attempt + 1} frames — "
                     f"terrain Y at origin: {test_hit:.1f}")
                physx_ready = True
                break
        except Exception:
            pass

    if not physx_ready:
        _log("WARNING: PhysX test raycast at origin missed after 60 frames — "
             "terrain coverage may be partial, continuing anyway")
        for _ in range(20):
            await app.next_update_async()

    # ---- 4. Read Cesium transform from live stage ----
    from pxr import Gf
    cesium_prim = stage.GetPrimAtPath("/CesiumGeoreference")
    if not cesium_prim or not cesium_prim.IsValid():
        print(f"{_TAG} ERROR: /CesiumGeoreference not found")
        return
    ecef_attr = cesium_prim.GetAttribute("cesium:ecefToUsdTransform")
    if not ecef_attr or not ecef_attr.IsValid():
        print(f"{_TAG} ERROR: cesium:ecefToUsdTransform not found")
        return
    ecef_to_usd_matrix = ecef_attr.Get()
    _log("Cesium transform loaded")

    def latlon_to_scene(lat, lon):
        ecef = _lat_lon_to_ecef(lat, lon, 0.0)
        usd = _ecef_to_usd(ecef, ecef_to_usd_matrix)
        return usd[0], usd[1], usd[2]

    # ---- 5. Load OSM data ----
    osm_cache = _OSM_DIR / "osm_cache.json"
    if not osm_cache.exists():
        print(f"{_TAG} ERROR: {osm_cache} not found — run generate_roads.py first")
        return

    _log("Loading OSM cache ...")
    with open(osm_cache, "r", encoding="utf-8") as f:
        osm_data = json.load(f)
    _log(f"{len(osm_data['elements'])} OSM elements loaded")

    # ---- 6. Process roads with terrain raycasting ----
    _log("Processing roads ...")

    raw_nodes = {}
    ways = []
    for elem in osm_data["elements"]:
        if elem["type"] == "node":
            raw_nodes[elem["id"]] = (elem["lat"], elem["lon"])
        elif elem["type"] == "way":
            ways.append(elem)

    node_coords = {}      # node_id -> (x, cesium_y, z)
    node_terrain_y = {}   # node_id -> terrain_y (or None)
    adjacency = {}        # node_id -> [[neighbour_id, dist_cm], ...]
    buckets = {}          # category -> [road_data, ...]

    # First pass: convert all referenced nodes to scene coords
    for way in ways:
        for nid in way.get("nodes", []):
            if nid in node_coords:
                continue
            n = raw_nodes.get(nid)
            if not n:
                continue
            x, y, z = latlon_to_scene(*n)
            node_coords[nid] = (x, y, z)

    _log(f"{len(node_coords)} unique nodes converted to scene coords")

    # Raycast all nodes for terrain Y (batch)
    _log(f"Raycasting {len(node_coords)} node positions ...")
    hit_count = 0
    miss_count = 0
    for nid, (x, y, z) in node_coords.items():
        ty = _terrain_y(x, z)
        node_terrain_y[nid] = ty
        if ty is not None:
            hit_count += 1
        else:
            miss_count += 1

    _log(f"Raycasts: {hit_count} hits, {miss_count} misses")
    _log(f"Raycast stats: multi-surface={_raycast_stats['multi']}, "
         f"lowest-Y-chosen={_raycast_stats['lowest_chosen']}")

    hit_ys = [ty for ty in node_terrain_y.values() if ty is not None]
    avg_terrain_y = sum(hit_ys) / len(hit_ys) if hit_ys else 0.0
    _log(f"Average terrain Y from hits: {avg_terrain_y:.1f}")

    # --- Iterative grade-based spike removal ---
    # Real urban roads rarely exceed ~10% grade. Any pair of consecutive
    # road nodes whose Y difference implies a steeper grade is flagged;
    # the higher node is removed.  Iterating erodes elevated segments
    # (bridges, ramps, overpasses) from their edges inward.
    MAX_GRADE = 0.10
    total_spikes_removed = 0
    for iteration in range(50):
        flagged: set[int] = set()
        for way in ways:
            ids = [nid for nid in way.get("nodes", []) if nid in node_coords]
            for i in range(len(ids) - 1):
                a, b = ids[i], ids[i + 1]
                ya = node_terrain_y.get(a)
                yb = node_terrain_y.get(b)
                if ya is None or yb is None:
                    continue
                ax, _, az = node_coords[a]
                bx, _, bz = node_coords[b]
                dist = math.hypot(bx - ax, bz - az)
                if dist < 10.0:
                    continue
                if abs(yb - ya) / dist > MAX_GRADE:
                    if yb > ya:
                        flagged.add(b)
                    else:
                        flagged.add(a)
        if not flagged:
            break
        for nid in flagged:
            node_terrain_y[nid] = None
        total_spikes_removed += len(flagged)

    # Repair removed nodes: set Y to average of surviving road-neighbors
    repaired = 0
    for _repair_pass in range(5):
        repaired_this = 0
        for way in ways:
            ids = [nid for nid in way.get("nodes", []) if nid in node_coords]
            for i, nid in enumerate(ids):
                if node_terrain_y.get(nid) is not None:
                    continue
                nb_ys = []
                for j in (i - 1, i + 1):
                    if 0 <= j < len(ids):
                        ny = node_terrain_y.get(ids[j])
                        if ny is not None:
                            nb_ys.append(ny)
                if nb_ys:
                    node_terrain_y[nid] = sum(nb_ys) / len(nb_ys)
                    repaired_this += 1
        repaired += repaired_this
        if repaired_this == 0:
            break

    hit_ys = [ty for ty in node_terrain_y.values() if ty is not None]
    avg_terrain_y = sum(hit_ys) / len(hit_ys) if hit_ys else avg_terrain_y
    _log(f"Spike filter: {total_spikes_removed} grade violations removed "
         f"(>{MAX_GRADE*100:.0f}% slope), {repaired} nodes repaired from "
         f"neighbors, {iteration + 1} iterations, avg Y: {avg_terrain_y:.1f}")

    # Second pass: build roads with subdivision and terrain Y
    total_visual_points = 0
    total_roads = 0

    for way in ways:
        tags = way.get("tags", {})
        cat = categorise(tags)
        cls = class_of(cat)
        access = wheelchair_access(tags)
        resolved_ids = []

        for nid in way.get("nodes", []):
            if nid in node_coords:
                resolved_ids.append(nid)

        if len(resolved_ids) < 2:
            continue

        has_any_hit = any(
            node_terrain_y.get(nid) is not None for nid in resolved_ids
        )
        if not has_any_hit:
            continue

        # Build adjacency (uses XZ distance, unaffected by Y)
        for i in range(len(resolved_ids) - 1):
            a, b = resolved_ids[i], resolved_ids[i + 1]
            ax, _, az = node_coords[a]
            bx, _, bz = node_coords[b]
            dist = _distance_cm(ax, az, bx, bz)
            adjacency.setdefault(a, []).append([b, dist, cls, access])
            adjacency.setdefault(b, []).append([a, dist, cls, access])

        # Build visual road with subdivision (Y is interpolated, not raycasted)
        road_points = []
        for i, nid in enumerate(resolved_ids):
            x, _, z = node_coords[nid]
            ty = node_terrain_y.get(nid)
            final_y = ty if ty is not None else avg_terrain_y

            if i == 0:
                road_points.append((x, final_y, z))
            else:
                prev_nid = resolved_ids[i - 1]
                prev_x, _, prev_z = node_coords[prev_nid]
                prev_ty = node_terrain_y.get(prev_nid)
                prev_y = prev_ty if prev_ty is not None else avg_terrain_y

                for sx, sz in _subdivide_segment(prev_x, prev_z, x, z):
                    if sx == x and sz == z:
                        sub_y = final_y
                    else:
                        dx_total = x - prev_x
                        dz_total = z - prev_z
                        seg_total = math.hypot(dx_total, dz_total)
                        if seg_total > 0:
                            t = math.hypot(sx - prev_x, sz - prev_z) / seg_total
                        else:
                            t = 0.5
                        sub_y = prev_y + (final_y - prev_y) * t
                    road_points.append((sx, sub_y, sz))

        buckets.setdefault(cat, []).append(road_points)
        total_roads += 1
        total_visual_points += len(road_points)

    _log(f"{total_roads} roads, {total_visual_points} visual points "
         f"(after subdivision)")

    # ---- 7. Write USDA ----
    _log("Writing USDA ...")

    usda_lines = [
        '#usda 1.0',
        '(',
        '    metersPerUnit = 0.01',
        '    upAxis = "Y"',
        ')',
        '',
        'def Xform "OSM_Roads"',
        '{',
    ]

    for cat, roads in buckets.items():
        style = ROAD_STYLES.get(cat, ROAD_STYLES["residential"])
        r, g, b = style["color"]
        w = style["width"]
        y_off = style.get("y_offset", 0) + ROAD_HOVER_CM

        all_points = []
        counts = []
        for road in roads:
            counts.append(len(road))
            all_points.extend(road)

        pts_str = ", ".join(
            f"({p[0]:.2f}, {p[1] + y_off:.2f}, {p[2]:.2f})" for p in all_points
        )
        counts_str = ", ".join(str(c) for c in counts)
        widths_str = ", ".join(f"{w:.1f}" for _ in all_points)

        usda_lines.append(f'    def BasisCurves "{cat}"')
        usda_lines.append( '    {')
        usda_lines.append(f'        uniform token type = "linear"')
        usda_lines.append(f'        int[] curveVertexCounts = [{counts_str}]')
        usda_lines.append(f'        point3f[] points = [{pts_str}]')
        usda_lines.append(f'        float[] widths = [{widths_str}]')
        usda_lines.append(f'        color3f[] primvars:displayColor = [({r}, {g}, {b})]')
        usda_lines.append( '    }')
        usda_lines.append( '')

    usda_lines.append('}')

    usda_path = _OSM_DIR / "gothenburg_roads.usda"
    with open(usda_path, "w", encoding="utf-8") as f:
        f.write("\n".join(usda_lines))
    _log(f"Saved: {usda_path}")

    # ---- 8. Write graph JSON ----
    _log("Writing graph JSON ...")

    graph_nodes = {}
    for nid, (x, _, z) in node_coords.items():
        ty = node_terrain_y.get(nid)
        final_y = ty if ty is not None else avg_terrain_y
        graph_nodes[str(nid)] = [x, final_y, z]

    serialisable_adj = {
        str(k): [[str(nb), round(d, 1), cls, access] for nb, d, cls, access in neighbours]
        for k, neighbours in adjacency.items()
    }

    graph = {
        "meta": {
            "lat_ref": 57.6993,
            "lon_ref": 11.9877,
            "radius_m": 3000,
            "coord_system": "Cesium ecefToUsdTransform (world-space USD coords)",
            "terrain_baked": True,
            "schema_version": 3,
            "includes_railway": True,
            "adjacency_tuple": "[neighbour_id, dist_cm, class, wheelchair_access_or_null]",
        },
        "nodes": graph_nodes,
        "adjacency": serialisable_adj,
    }

    graph_path = _OSM_DIR / "gothenburg_graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph, f)
    _log(f"Saved: {graph_path}")

    _log("Bake complete! Shutting down ...")
    await asyncio.sleep(1.0)
    app.post_quit()


async def _safe_bake():
    try:
        await _bake()
    except Exception:
        import traceback
        _log(f"FATAL ERROR:\n{traceback.format_exc()}")
        omni.kit.app.get_app().post_quit()

asyncio.ensure_future(_safe_bake())
