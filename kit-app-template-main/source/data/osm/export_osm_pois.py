"""
Fetch tagged POIs from OpenStreetMap (Overpass API) around the same area as
`generate_roads.py`, classify into dev-IoT categories, cap counts, write
`osm_pois_gbg.json` for the web + Kit open_data_live OSM markers.

Run from repo (or this directory):
    python export_osm_pois.py

Requires: network. Optional: `pip` not needed — stdlib only.

Re-run when you want fresher OSM data (same workflow as regenerating roads).
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

# Align with generate_roads.py
LAT_REF = 57.6993
LON_REF = 11.9877
RADIUS_M = 3000

OUT_FILE = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "osm_pois_gbg.json")
)

# Per-category limits after distance sort (closest first).
CAPS: dict[str, int] = {
    "restaurants": 400,
    "cafes_bars": 400,
    "parks": 200,
    "culture": 150,
    "transit_stops": 800,
}

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _classify(tags: dict[str, Any]) -> str | None:
    """Map OSM tags to a single UI/Kit category (priority order)."""
    if not tags:
        return None
    if tags.get("highway") == "bus_stop":
        return "transit_stops"
    pt = tags.get("public_transport")
    if pt in ("platform", "stop_position"):
        return "transit_stops"
    if tags.get("railway") == "tram_stop":
        return "transit_stops"

    amenity = tags.get("amenity")
    if amenity == "restaurant":
        return "restaurants"
    if amenity in ("cafe", "bar", "pub", "fast_food", "biergarten"):
        return "cafes_bars"
    if tags.get("leisure") == "park":
        return "parks"
    tourism = tags.get("tourism")
    if tourism in ("museum", "gallery", "attraction", "artwork"):
        return "culture"
    return None


def _overpass_query() -> str:
    lat, lon, r = LAT_REF, LON_REF, RADIUS_M
    # Union of node queries inside radius (nodes only for v1 — matches plan).
    return (
        f"[out:json][timeout:180];"
        f"("
        f'  node["amenity"="restaurant"](around:{r},{lat},{lon});'
        f'  node["amenity"="cafe"](around:{r},{lat},{lon});'
        f'  node["amenity"="bar"](around:{r},{lat},{lon});'
        f'  node["amenity"="pub"](around:{r},{lat},{lon});'
        f'  node["amenity"="fast_food"](around:{r},{lat},{lon});'
        f'  node["amenity"="biergarten"](around:{r},{lat},{lon});'
        f'  node["leisure"="park"](around:{r},{lat},{lon});'
        f'  node["tourism"="museum"](around:{r},{lat},{lon});'
        f'  node["tourism"="gallery"](around:{r},{lat},{lon});'
        f'  node["tourism"="attraction"](around:{r},{lat},{lon});'
        f'  node["tourism"="artwork"](around:{r},{lat},{lon});'
        f'  node["highway"="bus_stop"](around:{r},{lat},{lon});'
        f'  node["public_transport"="platform"](around:{r},{lat},{lon});'
        f'  node["public_transport"="stop_position"](around:{r},{lat},{lon});'
        f'  node["railway"="tram_stop"](around:{r},{lat},{lon});'
        f");"
        f"out body;"
    )


def fetch_overpass() -> dict[str, Any]:
    query = _overpass_query()
    print("Fetching POI nodes from Overpass API …")
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        _OVERPASS_URL,
        data=body,
        headers={"User-Agent": "Goteverse-OSM-POI/1.0"},
    )
    with urllib.request.urlopen(req, timeout=200) as resp:
        data = json.loads(resp.read().decode())
    print(f"  {len(data.get('elements', []))} elements")
    return data


def build_pois(osm_data: dict[str, Any]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in CAPS}

    for elem in osm_data.get("elements", []):
        if elem.get("type") != "node":
            continue
        tags = elem.get("tags") or {}
        cat = _classify(tags)
        if not cat:
            continue
        nid = elem.get("id")
        lat = elem.get("lat")
        lon = elem.get("lon")
        if nid is None or lat is None or lon is None:
            continue
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        if not name:
            # Human-readable fallback for list UI
            parts = []
            if tags.get("amenity"):
                parts.append(str(tags["amenity"]).replace("_", " "))
            if tags.get("highway") == "bus_stop":
                parts.append("bus stop")
            elif tags.get("public_transport"):
                parts.append(str(tags.get("public_transport")))
            elif tags.get("railway"):
                parts.append(str(tags.get("railway")).replace("_", " "))
            name = " ".join(parts).strip() or f"OSM node {nid}"
        oh = tags.get("opening_hours")
        detail_parts = []
        if amenity := tags.get("amenity"):
            detail_parts.append(f"amenity={amenity}")
        if tags.get("highway"):
            detail_parts.append(f"highway={tags['highway']}")
        if tags.get("public_transport"):
            detail_parts.append(f"public_transport={tags['public_transport']}")
        if tags.get("railway"):
            detail_parts.append(f"railway={tags['railway']}")
        if tags.get("leisure"):
            detail_parts.append(f"leisure={tags['leisure']}")
        if tags.get("tourism"):
            detail_parts.append(f"tourism={tags['tourism']}")

        dist = _haversine_m(LAT_REF, LON_REF, float(lat), float(lon))
        buckets[cat].append(
            {
                "id": f"osm_n{nid}",
                "lat": float(lat),
                "lon": float(lon),
                "name": name[:200],
                "category": cat,
                "distance_m": round(dist, 1),
                "opening_hours": str(oh)[:120] if oh else "",
                "detail": ", ".join(detail_parts)[:300],
            }
        )

    for cat in buckets:
        buckets[cat].sort(key=lambda x: x["distance_m"])
        cap = CAPS[cat]
        buckets[cat] = buckets[cat][:cap]

    out: list[dict[str, Any]] = []
    for cat in CAPS:
        out.extend(buckets[cat])
    return out


def main() -> None:
    raw = fetch_overpass()
    pois = build_pois(raw)
    payload = {
        "meta": {
            "schema_version": 1,
            "lat_ref": LAT_REF,
            "lon_ref": LON_REF,
            "radius_m": RADIUS_M,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "caps": CAPS,
            "source": "OpenStreetMap via Overpass API — ODbL",
        },
        "pois": pois,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(pois)} POIs to {OUT_FILE}")
    by_cat: dict[str, int] = {}
    for p in pois:
        c = p["category"]
        by_cat[c] = by_cat.get(c, 0) + 1
    print("  By category:", ", ".join(f"{k}={v}" for k, v in sorted(by_cat.items())))


if __name__ == "__main__":
    main()
