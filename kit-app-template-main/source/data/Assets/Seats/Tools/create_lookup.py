"""Create seats_lookup.json for ALL navigable seats (not filtered by availability).

Reads the full seat list from extracted_seats_with_rows.json (and any event
seat files like extracted_event_seats.json) plus the world transform from the
composed main_scene.usda.  Seat IDs use the full format (e.g. "A-4-15").
This ensures the lookup always contains every seat so the Kit extension can
distinguish "not found" from "not available" at runtime.

Re-run this script after editing Skandinavium ``seats_instanced`` (or ancestor)
transforms in USD (e.g. ``scandinavium_project_overrides.usda``) so
``seats_lookup.json`` matches the composed ``SeatInstancer`` world matrix.

Local XY matches ``generate_instancer.py`` (``visual_seat_xy_mm`` from
``seat_pivot_offset.py``) so navigation targets align with PointInstancer
instance origins. Z stays from seat JSON. Prototype-only mesh tweaks under
``Prototypes/*`` are still not applied here.

Wheelchair spots are included (they share the same parent transform).
Companion (MEDFÖLJARE) seats are excluded — they are visual-only and not
navigable.

Requires: pxr (OpenUSD)
"""

import json
import os
from pxr import Usd, UsdGeom, Gf

from seat_pivot_offset import visual_seat_xy_mm

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEATS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SEATS_DIR, "Data")
SEATS_JSON = os.path.join(DATA_DIR, "extracted_seats_with_rows.json")
EVENT_SEATS_JSON = os.path.join(DATA_DIR, "extracted_event_seats.json")
MAIN_SCENE = os.path.join(SEATS_DIR, "..", "..", "scenes", "main_scene.usda")
OUTPUT = os.path.join(SEATS_DIR, "..", "..", "..", "extensions",
                      "younite.navmesh_route_extension", "config", "seats_lookup.json")

INSTANCER_PRIM_PATH = "/World/Skandinavium/seats_instanced/SeatInstancer"


def main():
    with open(SEATS_JSON, encoding="utf-8") as f:
        seats = json.load(f)
    print(f"Loaded {len(seats)} seats from extracted_seats_with_rows.json")

    # Merge event seats (adds new IDs like PARKETT-* without overwriting)
    extra_count = 0
    if os.path.isfile(EVENT_SEATS_JSON):
        with open(EVENT_SEATS_JSON, encoding="utf-8") as f:
            event_seats = json.load(f)
        existing_ids = {s["id"] for s in seats}
        for s in event_seats:
            if s["id"] not in existing_ids:
                seats.append(s)
                extra_count += 1
        print(f"  Merged {extra_count} new seats from "
              f"{os.path.basename(EVENT_SEATS_JSON)} "
              f"(total {len(seats)})")

    scene_path = os.path.normpath(MAIN_SCENE)
    print(f"Opening {scene_path} for world transform...")
    stage = Usd.Stage.Open(scene_path)
    if not stage:
        raise RuntimeError(f"Failed to open stage: {scene_path}")

    prim = stage.GetPrimAtPath(INSTANCER_PRIM_PATH)
    if not prim.IsValid():
        raise RuntimeError(f"Prim not found: {INSTANCER_PRIM_PATH}")

    xformable = UsdGeom.Xformable(prim)
    world_mtx = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())

    navigable = [s for s in seats if s.get("tier") != "companion"]
    skipped = len(seats) - len(navigable)
    print(f"Building world-space lookup ({len(navigable)} navigable, "
          f"{skipped} companion excluded)...")

    lookup = {}
    for s in navigable:
        lx, ly = visual_seat_xy_mm(s)
        local_pos = Gf.Vec3d(lx, ly, s.get("z", 0.0))
        world_pos = world_mtx.Transform(local_pos)
        lookup[s["id"]] = [round(world_pos[0], 1),
                           round(world_pos[1], 1),
                           round(world_pos[2], 1)]

    os.makedirs(os.path.dirname(os.path.normpath(OUTPUT)), exist_ok=True)
    out_path = os.path.normpath(OUTPUT)
    with open(out_path, 'w') as f:
        json.dump(lookup, f, separators=(',', ':'))

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\nCreated {out_path}")
    print(f"  {len(lookup)} seats, {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
