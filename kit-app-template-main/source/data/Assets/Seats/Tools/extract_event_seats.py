"""Extract event seating from the Playstation C DXF.

Strategy:
  1. Start from the original full seat data (extracted_seats_with_rows.json).
  2. Remove seats via two mechanisms:
     a. **Color=9 STOLAR rectangles** — individual LWPOLYLINE entities on
        STOLAR* layers with ACI color 9, matched to the nearest STOLNUMMER
        label to find the seat position.
     b. **Explicit section/tier rules** for the event layout:
        - Sections K, L, M → remove ALL seats (every tier).
        - Sections J, N   → remove ALL seats, except a small whitelist
          of specific lower-tier seats that remain.
  3. Parse Parkettstolar INSERT entities (arena floor seats) and add them
     at the same Z-height as row 0.

Requires: ezdxf, numpy
"""

import ezdxf
import json
import math
import os
from collections import defaultdict

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEATS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SEATS_DIR, "Data")

EVENT_DXF_PATH = os.path.join(
    DATA_DIR, "240904 Playstation C  Seating  (V1).dxf")
ORIGINAL_SEATS_PATH = os.path.join(DATA_DIR, "extracted_seats_with_rows.json")
ROW_HEIGHTS_PATH = os.path.join(DATA_DIR, "row_heights.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "extracted_event_seats.json")

INACTIVE_COLOR = 9
PARKETT_MIN_X = 0
SEAT_MATCH_TOLERANCE = 500

# Sections where ALL seats are removed for the event
REMOVE_ALL_SECTIONS = {"K", "L", "M"}
# Sections where ALL seats are removed EXCEPT specific whitelisted IDs
REMOVE_EXCEPT_WHITELIST_SECTIONS = {"J", "N"}
KEEP_SEAT_IDS = {
    "J-0-1", "J-0-2", "J-1-1", "J-2-1", "J-3-1", "J-4-1",
    "N-0-20", "N-1-21", "N-2-23", "N-3-23",
}
# Individual seats to remove (not caught by color=9 or section rules)
REMOVE_SEAT_IDS = {
    "H-33-55", "H-33-56", "H-33-57", "H-33-58", "H-33-59", "H-34-54",
    "P-30-1", "P-31-1", "P-32-1", "P-33-1", "P-33-2", "P-33-3",
    "P-33-4", "P-33-5", "P-33-6", "P-34-1",
}


# ---------------------------------------------------------------------------
# Color=9 rectangle detection
# ---------------------------------------------------------------------------

def find_inactive_rect_positions(dxf_path):
    """Find positions of individually-marked inactive seats.

    Scans for LWPOLYLINE entities with color=9 on STOLAR* layers,
    matches each to the nearest STOLNUMMER TEXT label, and returns
    the label positions.
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    rects = []
    for e in msp:
        if e.dxftype() != "LWPOLYLINE":
            continue
        layer = e.dxf.layer.strip()
        if "STOLAR" not in layer:
            continue
        color = e.dxf.color if hasattr(e.dxf, "color") else 256
        if color != INACTIVE_COLOR:
            continue
        pts = list(e.get_points(format="xy"))
        if not pts:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        rects.append((cx, cy))

    all_labels = []
    for e in msp.query("TEXT"):
        layer = e.dxf.layer.strip()
        if "STOLNUMMER" not in layer or "RULLSTOL" in layer:
            continue
        all_labels.append((e.dxf.insert.x, e.dxf.insert.y))

    matched = []
    for rx, ry in rects:
        best_dist = float("inf")
        best = None
        for lx, ly in all_labels:
            d = math.hypot(lx - rx, ly - ry)
            if d < best_dist:
                best_dist = d
                best = (lx, ly)
        if best and best_dist < 1000:
            matched.append(best)

    return matched, len(rects)


# ---------------------------------------------------------------------------
# Remove inactive seats
# ---------------------------------------------------------------------------

def remove_inactive_seats(original_seats, inactive_positions):
    """Remove seats that are inactive for the event.

    A seat is removed if:
      1. id in REMOVE_SEAT_IDS, OR
      2. section in REMOVE_ALL_SECTIONS, OR
      3. section in REMOVE_EXCEPT_WHITELIST_SECTIONS and id NOT in
         KEEP_SEAT_IDS, OR
      4. its (x, y) matches a color=9 rect position within tolerance.
    """
    # Indices of whitelisted seats — never remove these
    protected = set()
    for i, s in enumerate(original_seats):
        if s.get("id") in KEEP_SEAT_IDS:
            protected.add(i)

    grid = defaultdict(list)
    for i, s in enumerate(original_seats):
        gx = int(s["x"] // 1000)
        gy = int(s["y"] // 1000)
        grid[(gx, gy)].append(i)

    remove_indices = set()
    removed_by_section = 0
    removed_by_rect = 0

    for i, s in enumerate(original_seats):
        if i in protected:
            continue
        sec = s.get("section", "")
        sid = s.get("id", "")

        if sid in REMOVE_SEAT_IDS:
            remove_indices.add(i)
            removed_by_section += 1
        elif sec in REMOVE_ALL_SECTIONS:
            remove_indices.add(i)
            removed_by_section += 1
        elif sec in REMOVE_EXCEPT_WHITELIST_SECTIONS:
            remove_indices.add(i)
            removed_by_section += 1

    for ix, iy in inactive_positions:
        gx = int(ix // 1000)
        gy = int(iy // 1000)
        best_dist = float("inf")
        best_idx = None
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for idx in grid.get((gx + dx, gy + dy), []):
                    if idx in remove_indices or idx in protected:
                        continue
                    s = original_seats[idx]
                    d = math.hypot(s["x"] - ix, s["y"] - iy)
                    if d < best_dist:
                        best_dist = d
                        best_idx = idx
        if best_idx is not None and best_dist <= SEAT_MATCH_TOLERANCE:
            remove_indices.add(best_idx)
            removed_by_rect += 1

    filtered = [s for i, s in enumerate(original_seats)
                if i not in remove_indices]
    return filtered, removed_by_section, removed_by_rect


# ---------------------------------------------------------------------------
# Parkettstolar (arena floor seats)
# ---------------------------------------------------------------------------

def parse_parkettstolar(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    seats = []
    for e in msp.query('INSERT[layer=="Parkettstolar"]'):
        if e.dxf.insert.x < PARKETT_MIN_X:
            continue
        seats.append(dict(
            x=e.dxf.insert.x, y=e.dxf.insert.y,
            rotation=float(getattr(e.dxf, "rotation", 0.0)),
        ))
    return seats


def assign_parkett_rows_and_seats(seats, floor_z, col_tolerance=300):
    if not seats:
        return []
    seats_sorted = sorted(seats, key=lambda s: s["x"])
    columns = []
    cur_col = [seats_sorted[0]]
    for s in seats_sorted[1:]:
        if abs(s["x"] - cur_col[-1]["x"]) <= col_tolerance:
            cur_col.append(s)
        else:
            columns.append(cur_col)
            cur_col = [s]
    columns.append(cur_col)
    columns.sort(key=lambda col: np.mean([s["x"] for s in col]))
    n_cols = len(columns)

    results = []
    for col_idx, col in enumerate(columns):
        row_num = n_cols - col_idx
        col.sort(key=lambda s: s["y"])
        for seat_idx, s in enumerate(col):
            results.append(dict(
                id=f"PARKETT-{row_num}-{seat_idx + 1}",
                section="PARKETT", row=int(row_num),
                seat_number=str(seat_idx + 1), tier="parkett",
                x=round(s["x"], 2), y=round(s["y"], 2), z=floor_z,
                rotation=round(s["rotation"], 2),
            ))
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Loading original seat data: {os.path.basename(ORIGINAL_SEATS_PATH)}")
    with open(ORIGINAL_SEATS_PATH, encoding="utf-8") as f:
        original_seats = json.load(f)
    print(f"  {len(original_seats)} seats (baseline)")

    with open(ROW_HEIGHTS_PATH, encoding="utf-8") as f:
        row_heights = json.load(f)
    floor_z = row_heights.get("0", 16337)
    print(f"  Floor seat Z height (row 0): {floor_z}")

    # ── Section/tier counts before removal ──
    print(f"\n  Section removal rules:")
    for sec in sorted(REMOVE_ALL_SECTIONS):
        n = sum(1 for s in original_seats if s.get("section") == sec)
        print(f"    {sec}: remove ALL ({n} seats)")
    for sec in sorted(REMOVE_EXCEPT_WHITELIST_SECTIONS):
        total = sum(1 for s in original_seats if s.get("section") == sec)
        kept = sum(1 for s in original_seats
                   if s.get("section") == sec and s.get("id") in KEEP_SEAT_IDS)
        print(f"    {sec}: remove all except {kept} whitelisted ({total} total, "
              f"removing {total - kept})")

    # ── Color=9 rectangles ──
    print(f"\nScanning event DXF for color={INACTIVE_COLOR} STOLAR rectangles...")
    inactive_positions, n_rects = find_inactive_rect_positions(EVENT_DXF_PATH)
    print(f"  Found {n_rects} color={INACTIVE_COLOR} rectangles, "
          f"matched {len(inactive_positions)} to labels")

    # ── Remove ──
    print(f"\nRemoving inactive seats...")
    filtered_seats, removed_section, removed_rect = \
        remove_inactive_seats(original_seats, inactive_positions)
    print(f"  Removed by section rules: {removed_section}")
    print(f"  Removed by color=9 rects: {removed_rect}")
    print(f"  Total removed: {removed_section + removed_rect}")
    print(f"  Remaining: {len(filtered_seats)}")

    remaining = defaultdict(lambda: defaultdict(int))
    for s in filtered_seats:
        remaining[s.get("section", "?")][s.get("tier", "?")] += 1
    print(f"\n  Remaining per section/tier:")
    for sec in sorted(remaining.keys()):
        tiers = remaining[sec]
        parts = ", ".join(f"{t}={c}" for t, c in sorted(tiers.items()))
        total = sum(tiers.values())
        print(f"    {sec}: {total}  ({parts})")

    # ── Parkettstolar ──
    print(f"\nParsing Parkettstolar floor seats...")
    parkett_raw = parse_parkettstolar(EVENT_DXF_PATH)
    print(f"  Raw floor seats: {len(parkett_raw)} (filtered X > {PARKETT_MIN_X})")

    parkett_results = assign_parkett_rows_and_seats(parkett_raw, floor_z)
    print(f"  Floor seat results: {len(parkett_results)}")

    if parkett_results:
        rows = sorted(set(r["row"] for r in parkett_results))
        print(f"  Rows: {len(rows)} (range {rows[0]}-{rows[-1]})")

    # ── Combine ──
    results = filtered_seats + parkett_results

    n_wc = sum(1 for s in filtered_seats if s.get("tier") == "wheelchair")
    print(f"\n{'='*70}")
    print(f" SUMMARY")
    print(f"{'='*70}")
    print(f"  Original seats:       {len(original_seats)}")
    print(f"  Removed (sections):   {removed_section}")
    print(f"  Removed (color=9):    {removed_rect}")
    print(f"  Remaining regular:    {len(filtered_seats)} (incl. {n_wc} wheelchair)")
    print(f"  Floor seats added:    {len(parkett_results)}")
    print(f"  Total event seats:    {len(results)}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
