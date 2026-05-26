"""
One-shot script: fetch Gothenburg road + railway network from OSM and produce:
  1. gothenburg_roads.usda  — visual BasisCurves (colour-coded by road / rail type)
  2. gothenburg_graph.json  — pathfinding graph (nodes + bidirectional adjacency)

Highway ways: ``highway=*`` (motorway … cycleway) as before.

Railway ways: ``railway=tram|light_rail|rail|subway|…`` in the same-radius
Overpass query (union). Edge ``class`` in the graph JSON is ``tram``,
``light_rail``, or ``rail_heavy`` — consumed by ``OsmGraphService.MODE_COSTS``
modes ``tram`` / ``train`` / ``car`` / etc.

Ferries are not fetched (separate data model). Delete ``osm_cache.json`` and
re-run, or use ``--force`` / ``set OSM_FORCE_REFETCH=1`` to refetch after
 changing filters.

Coordinate conversion uses the Cesium georeference (ecefToUsdTransform) from
main_scene.usda so that features align with the Cesium terrain tiles. **Y is
ellipsoid height here** — run ``bake_roads.bat`` (Kit ``bake_terrain_roads.py``)
for terrain-following Y in ``gothenburg_graph.json`` / ``gothenburg_roads.usda``.

Requires: pxr (OpenUSD)
"""

import json
import math
import os
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LAT_REF = 57.6993
LON_REF = 11.9877
RADIUS_M = 3000

MAIN_SCENE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "scenes", "main_scene.usda",
))

# WGS-84 ellipsoid
_WGS84_A = 6_378_137.0
_WGS84_B = 6_356_752.314245
_WGS84_E2 = 1.0 - (_WGS84_B ** 2) / (_WGS84_A ** 2)

HIGHWAY_FILTER = (
    "motorway|trunk|primary|secondary|tertiary|"
    "residential|unclassified|living_street|"
    "footway|pedestrian|path|cycleway|steps"
)

# ``railway=*`` values to pull from Overpass (excludes disused / abandoned —
# not useful for live routing; add there if you need disused for visuals).
RAILWAY_FILTER = (
    "tram|light_rail|rail|subway|narrow_gauge|preserved|monorail|construction"
)

ROAD_STYLES = {
    "motorway":    {"color": (0.90, 0.15, 0.15), "width": 1400, "y_offset": 0},
    "trunk":       {"color": (0.95, 0.45, 0.10), "width": 1000, "y_offset": 20},
    "primary":     {"color": (0.95, 0.80, 0.15), "width": 700,  "y_offset": 40},
    "secondary":   {"color": (0.35, 0.65, 0.90), "width": 600,  "y_offset": 60},
    "tertiary":    {"color": (0.35, 0.80, 0.35), "width": 500,  "y_offset": 80},
    "residential": {"color": (0.72, 0.72, 0.72), "width": 400,  "y_offset": 100},
    "pedestrian":  {"color": (0.85, 0.65, 0.90), "width": 250,  "y_offset": 120},
    "steps":       {"color": (0.60, 0.40, 0.25), "width": 150,  "y_offset": 130},
    # Railway (distinct palette; narrow widths read as "tracks" at city scale)
    "rail_tram":       {"color": (0.95, 0.75, 0.10), "width": 120,  "y_offset": 5},
    "rail_light_rail": {"color": (0.20, 0.90, 0.85), "width": 130,  "y_offset": 5},
    "rail_subway":     {"color": (0.55, 0.20, 0.85), "width": 200,  "y_offset": 0},
    "rail_main":       {"color": (0.45, 0.35, 0.28), "width": 220,  "y_offset": 0},
}

# Coarser class used for mode-aware routing (see osm_graph_service.MODE_COSTS).
# Every *visual* category below maps to exactly one routing class string
# stored on each graph edge: road-style five-way + ``tram`` / ``light_rail`` /
# ``rail_heavy``.
CLASS_OF_CATEGORY = {
    "motorway":    "highway",
    "trunk":       "highway",
    "primary":     "arterial",
    "secondary":   "arterial",
    "tertiary":    "residential",
    "residential": "residential",
    "pedestrian":  "pedestrian",
    "steps":       "steps",
    "rail_tram":       "tram",
    "rail_light_rail": "light_rail",
    "rail_subway":     "rail_heavy",
    "rail_main":       "rail_heavy",
}

# Map OSM ``railway=*`` value → visual key in ROAD_STYLES
RAILWAY_VALUE_TO_VISUAL: dict[str, str] = {
    "tram":         "rail_tram",
    "light_rail":   "rail_light_rail",
    "subway":       "rail_subway",
    "rail":         "rail_main",
    "narrow_gauge": "rail_main",
    "preserved":    "rail_main",
    "monorail":     "rail_main",
    "construction": "rail_main",
}

# OSM wheelchair=* values we recognise. Anything else → None.
_WHEELCHAIR_VALUES = ("yes", "no", "limited")


# ---------------------------------------------------------------------------
# Coordinate conversion — Cesium-aligned (WGS-84 → ECEF → USD)
# ---------------------------------------------------------------------------

_ecef_to_usd_matrix = None  # set once in main


def _lat_lon_to_ecef(lat: float, lon: float, height: float = 0.0):
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    sin_lat = math.sin(lat_r)
    cos_lat = math.cos(lat_r)
    sin_lon = math.sin(lon_r)
    cos_lon = math.cos(lon_r)
    N = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat ** 2)
    x = (N + height) * cos_lat * cos_lon
    y = (N + height) * cos_lat * sin_lon
    z = (N * (1.0 - _WGS84_E2) + height) * sin_lat
    return (x, y, z)


def _ecef_to_usd(ecef_xyz, mtx):
    from pxr import Gf
    p = Gf.Vec4d(ecef_xyz[0], ecef_xyz[1], ecef_xyz[2], 1.0)
    r = p * mtx
    return (r[0], r[1], r[2])


def _read_cesium_transform():
    """Read cesium:ecefToUsdTransform from main_scene.usda."""
    from pxr import Usd, Gf
    if not os.path.isfile(MAIN_SCENE):
        raise FileNotFoundError(f"Scene not found: {MAIN_SCENE}")
    stage = Usd.Stage.Open(MAIN_SCENE)
    prim = stage.GetPrimAtPath("/CesiumGeoreference")
    if not prim or not prim.IsValid():
        raise RuntimeError("No /CesiumGeoreference prim in scene")
    attr = prim.GetAttribute("cesium:ecefToUsdTransform")
    if not attr or not attr.IsValid():
        raise RuntimeError("cesium:ecefToUsdTransform attribute not found")
    return attr.Get()


def latlon_to_scene(lat, lon):
    """Return (x, y, z) in USD scene coordinates using the Cesium transform."""
    ecef = _lat_lon_to_ecef(lat, lon, 0.0)
    usd = _ecef_to_usd(ecef, _ecef_to_usd_matrix)
    return usd[0], usd[1], usd[2]


def categorise_highway(tag: str) -> str:
    if tag in ("motorway",):
        return "motorway"
    if tag in ("trunk",):
        return "trunk"
    if tag in ("primary",):
        return "primary"
    if tag in ("secondary",):
        return "secondary"
    if tag in ("tertiary",):
        return "tertiary"
    if tag in ("residential", "living_street", "unclassified"):
        return "residential"
    if tag in ("footway", "pedestrian", "path", "cycleway"):
        return "pedestrian"
    if tag == "steps":
        return "steps"
    return "residential"


def categorise(tags: dict) -> str:
    """Return a visual / bucket key (``ROAD_STYLES``) for a way's tag dict."""
    rw = tags.get("railway")
    if rw is not None and str(rw).strip():
        k = str(rw).strip().lower()
        return RAILWAY_VALUE_TO_VISUAL.get(k, "rail_main")
    h = tags.get("highway", "residential")
    if h is None:
        h = "residential"
    return categorise_highway(str(h).strip() or "residential")


def class_of(category: str) -> str:
    """Map a visual category → routing class (``OsmGraphService`` edge class)."""
    return CLASS_OF_CATEGORY.get(category, "residential")


def wheelchair_access(tags):
    """Return 'yes' / 'no' / 'limited' / None from way.tags['wheelchair']."""
    val = tags.get("wheelchair")
    if val in _WHEELCHAIR_VALUES:
        return val
    return None


# ---------------------------------------------------------------------------
# Overpass API
# ---------------------------------------------------------------------------

CACHE_FILE = os.path.join(os.path.dirname(__file__), "osm_cache.json")


def fetch(force: bool = False) -> dict:
    force = force or os.environ.get("OSM_FORCE_REFETCH", "").strip() in (
        "1", "true", "yes", "y",
    )
    if os.path.exists(CACHE_FILE) and not force:
        print(f"Using cached OSM data from {CACHE_FILE}")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"  {len(data['elements'])} elements from cache")
        return data
    if force and os.path.exists(CACHE_FILE):
        print("OSM_FORCE_REFETCH=1 (or --force) — refetching, ignoring cache")

    # Union: carriageways + heavy / light / tram rail (ferries omitted).
    query = (
        f"[out:json][timeout:90];"
        f"("
        f'way["highway"~"^({HIGHWAY_FILTER})$"](around:{RADIUS_M},{LAT_REF},{LON_REF});'
        f'way["railway"~"^({RAILWAY_FILTER})$"](around:{RADIUS_M},{LAT_REF},{LON_REF});'
        f");"
        f"(._;>;);out body;"
    )
    print("Fetching from Overpass API …")
    url = "https://overpass-api.de/api/interpreter"
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "OmniKit-OSM/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    print(f"  Got {len(data['elements'])} elements")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"  Cached to {CACHE_FILE}")
    return data


# ---------------------------------------------------------------------------
# Build USDA (visual) + graph JSON (pathfinding)
# ---------------------------------------------------------------------------

def _distance_cm(ax, az, bx, bz):
    return math.hypot(bx - ax, bz - az)


def build_outputs(osm_data):
    """Return (usda_text, graph_dict)."""

    # --- index nodes and ways ------------------------------------------------
    raw_nodes = {}
    ways = []
    for elem in osm_data["elements"]:
        if elem["type"] == "node":
            raw_nodes[elem["id"]] = (elem["lat"], elem["lon"])
        elif elem["type"] == "way":
            ways.append(elem)

    # --- convert to scene coords, bucket visuals, build adjacency ------------
    node_coords = {}  # node_id -> (x, y, z)
    adjacency = {}    # node_id -> [[neighbour_id, dist_cm], ...]
    buckets = {}      # category -> [[(x,y,z), ...], ...]

    for way in ways:
        tags = way.get("tags", {})
        cat = categorise(tags)
        cls = class_of(cat)
        access = wheelchair_access(tags)
        road_coords = []
        resolved_ids = []

        for nid in way.get("nodes", []):
            n = raw_nodes.get(nid)
            if not n:
                continue
            if nid not in node_coords:
                x, y, z = latlon_to_scene(*n)
                node_coords[nid] = (x, y, z)
            road_coords.append(node_coords[nid])
            resolved_ids.append(nid)

        if len(resolved_ids) < 2:
            continue

        buckets.setdefault(cat, []).append(road_coords)

        for i in range(len(resolved_ids) - 1):
            a, b = resolved_ids[i], resolved_ids[i + 1]
            ax, _, az = node_coords[a]
            bx, _, bz = node_coords[b]
            dist = _distance_cm(ax, az, bx, bz)
            adjacency.setdefault(a, []).append([b, dist, cls, access])
            adjacency.setdefault(b, []).append([a, dist, cls, access])

    # --- build USDA text -----------------------------------------------------
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

    total_roads = 0
    for cat, roads in buckets.items():
        style = ROAD_STYLES.get(cat, ROAD_STYLES["residential"])
        r, g, b = style["color"]
        w = style["width"]
        y_off = style.get("y_offset", 0)

        all_points = []
        counts = []
        for road in roads:
            counts.append(len(road))
            all_points.extend(road)

        pts_str = ", ".join(f"({p[0]:.2f}, {p[1] + y_off:.2f}, {p[2]:.2f})" for p in all_points)
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
        total_roads += len(roads)

    usda_lines.append('}')
    print(f"  {total_roads} road segments across {len(buckets)} categories")

    # --- build graph dict ----------------------------------------------------
    serialisable_nodes = {str(k): list(v) for k, v in node_coords.items()}
    serialisable_adj = {
        str(k): [[str(nb), round(d, 1), cls, access] for nb, d, cls, access in neighbours]
        for k, neighbours in adjacency.items()
    }

    graph = {
        "meta": {
            "lat_ref": LAT_REF,
            "lon_ref": LON_REF,
            "radius_m": RADIUS_M,
            "coord_system": "Cesium ecefToUsdTransform (world-space USD coords)",
            "schema_version": 3,
            "includes_railway": True,
            "adjacency_tuple": (
                "[neighbour_id, dist_cm, class, wheelchair_access_or_null] "
                "— class is road (pedestrian|steps|residential|arterial|highway) "
                "or rail (tram|light_rail|rail_heavy)"
            ),
        },
        "nodes": serialisable_nodes,
        "adjacency": serialisable_adj,
    }
    print(f"  {len(serialisable_nodes)} graph nodes, {sum(len(v) for v in serialisable_adj.values()) // 2} edges")

    return "\n".join(usda_lines), graph


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Fetch OSM roads + railway, emit USDA + graph JSON")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Ignore osm_cache.json and refetch from Overpass (same as OSM_FORCE_REFETCH=1)",
    )
    args = ap.parse_args()

    out_dir = os.path.dirname(os.path.abspath(__file__))

    print(f"Reading Cesium georeference from {MAIN_SCENE} …")
    _ecef_to_usd_matrix = _read_cesium_transform()
    print("  Transform matrix loaded")

    data = fetch(force=args.force)
    usda_text, graph_data = build_outputs(data)

    usda_path = os.path.join(out_dir, "gothenburg_roads.usda")
    with open(usda_path, "w", encoding="utf-8") as f:
        f.write(usda_text)
    print(f"Saved: {usda_path}")

    graph_path = os.path.join(out_dir, "gothenburg_graph.json")
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f)
    print(f"Saved: {graph_path}")
    print(
        "Note: Y is ellipsoid/Cesium height only — curves do NOT hug terrain yet.\n"
        "      From kit-app-template-main root, run:  source\\data\\osm\\bake_roads.bat\n"
        "      (Kit + PhysX raycast bake). Run repo.bat from that root so --exec paths resolve."
    )
