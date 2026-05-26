"""Extract seat data from Skandinavium DXF — two-phase pipeline.

Phase 1 — TELE seats:
  Section assignment via angular wedges (SEKTIONER divider lines).
  Row assignment via fan-sweep (rotate, sort, k-gap).

Phase 2 — Upper seats:
  Section from DXF layer name (already correct).
  Row assignment via fan-sweep.

The two phases are completely independent — no shared mutable state.

Requires: ezdxf, numpy
"""

import ezdxf
import json
import math
import os
import random
from collections import Counter, defaultdict

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEATS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SEATS_DIR, "Data")
DXF_PATH = os.path.join(DATA_DIR, "260113 Scandinavium Arenaplan.dxf")
OUTPUT_PATH = os.path.join(DATA_DIR, "extracted_seats_with_rows.json")
BOUNDARIES_PATH = os.path.join(DATA_DIR, "tele_boundaries.json")
OVERRIDES_PATH = os.path.join(DATA_DIR, "section_overrides.json")
ROW_HEIGHTS_PATH = os.path.join(DATA_DIR, "row_heights.json")

# ---------------------------------------------------------------------------
# Layer classification
# ---------------------------------------------------------------------------

_LAYER_MAP = {
    "STOLNUMMER":        ("seat",      "upper"),
    "STOLNUMMER_TELE":   ("seat",      "lower"),
    "STOLNUMMER_TELE_2": ("seat",      "lower2"),
    "RADNUMMER":         ("row_label", "upper"),
    "RADNUMMER_TELE":    ("row_label", "lower"),
}


def classify_layer(layer: str):
    layer = layer.strip()
    if "STOLNR RULLSTOLSPLATS" in layer:
        return layer.split("-", 1)[0], "wheelchair", None
    if "EXTRA STOLNUMMER_TELE" in layer:
        return None, None, None
    if "-" not in layer:
        return None, None, None
    section, rest = layer.split("-", 1)
    section = section.rstrip("abcdefghijklmnopqrstuvwxyz")
    if rest in _LAYER_MAP:
        return section, *_LAYER_MAP[rest]
    return None, None, None


def _is_tele_tier(tier):
    return tier in ("lower", "lower2", "extra_lower")


# ---------------------------------------------------------------------------
# Local center of curvature
# ---------------------------------------------------------------------------

def _toward_center_sign(seats, gcx, gcy):
    """Return -1 if theta-90 points toward center, +1 if theta+90 does."""
    avg_x = float(np.mean([s["x"] for s in seats]))
    avg_y = float(np.mean([s["y"] for s in seats]))
    avg_t = math.radians(float(np.mean([s["rotation"] for s in seats])))

    to_c = (gcx - avg_x, gcy - avg_y)
    tc_len = math.hypot(*to_c)
    if tc_len < 1e-6:
        return -1
    tc = (to_c[0] / tc_len, to_c[1] / tc_len)

    d_minus = (math.sin(avg_t), -math.cos(avg_t))
    d_plus = (-math.sin(avg_t), math.cos(avg_t))

    return -1 if (d_minus[0] * tc[0] + d_minus[1] * tc[1]) >= \
                 (d_plus[0] * tc[0] + d_plus[1] * tc[1]) else 1


def estimate_center(seats, sign, max_pairs=3000, max_dist=400000):
    """Estimate center of curvature by intersecting toward-center rays.

    Uses the perpendicular to each seat's text rotation angle as the
    ray direction (pointing toward the local center of curvature).
    The median intersection gives a robust center estimate.
    """
    rads = [(s["x"], s["y"], math.radians(s["rotation"])) for s in seats]
    n = len(rads)
    if n < 3:
        return None

    random.seed(42)
    total_pairs = n * (n - 1) // 2
    if total_pairs <= max_pairs:
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    else:
        pairs = [tuple(random.sample(range(n), 2)) for _ in range(max_pairs)]

    intersections = []
    for i, j in pairs:
        x1, y1, t1 = rads[i]
        x2, y2, t2 = rads[j]
        if sign == -1:
            d1x, d1y = math.sin(t1), -math.cos(t1)
            d2x, d2y = math.sin(t2), -math.cos(t2)
        else:
            d1x, d1y = -math.sin(t1), math.cos(t1)
            d2x, d2y = -math.sin(t2), math.cos(t2)

        det = d1x * d2y - d1y * d2x
        if abs(det) < 1e-8:
            continue
        t = ((x2 - x1) * d2y - (y2 - y1) * d2x) / det
        if t <= 0:
            continue
        intersections.append((x1 + t * d1x, y1 + t * d1y))

    if len(intersections) < 3:
        return None

    cx = float(np.median([p[0] for p in intersections]))
    cy = float(np.median([p[1] for p in intersections]))

    scx = float(np.mean([s["x"] for s in seats]))
    scy = float(np.mean([s["y"] for s in seats]))
    if math.hypot(cx - scx, cy - scy) > max_dist:
        return None

    return (cx, cy)


# ---------------------------------------------------------------------------
# DXF parsing
# ---------------------------------------------------------------------------

def parse_dxf(dxf_path):
    """Parse seats, row labels, wheelchair, section letters, divider lines,
    and companion (MEDFÖLJARE) seat polylines."""
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    seats, row_labels, wheelchair = [], [], []
    companion_polys = []
    section_letters = {}

    for e in msp.query("TEXT"):
        layer = e.dxf.layer.strip()
        if layer == "SEKTIONS_NR":
            letter = e.dxf.text.strip()
            if letter:
                section_letters[letter] = dict(
                    x=e.dxf.insert.x, y=e.dxf.insert.y,
                    rotation=float(getattr(e.dxf, "rotation", 0.0)))
            continue
        section, cat, tier = classify_layer(layer)
        if cat is None:
            continue
        rec = dict(section=section, text=e.dxf.text.strip(), tier=tier,
                   x=e.dxf.insert.x, y=e.dxf.insert.y,
                   rotation=float(getattr(e.dxf, "rotation", 0.0)), layer=layer,
                   handle=e.dxf.handle)
        {"seat": seats, "row_label": row_labels, "wheelchair": wheelchair}[cat].append(rec)

    # Parse SEKTIONER radial divider lines
    divider_lines = []
    for e in msp:
        layer = e.dxf.layer.strip()
        if layer == "SEKTIONER" and e.dxftype() == "LINE":
            sx, sy = e.dxf.start.x, e.dxf.start.y
            ex, ey = e.dxf.end.x, e.dxf.end.y
            length = math.hypot(ex - sx, ey - sy)
            if length > 3000:
                divider_lines.append(dict(sx=sx, sy=sy, ex=ex, ey=ey,
                                         length=length))

        # Companion (MEDFÖLJARE) seats — LWPOLYLINE rectangles on
        # "*-STOLAR MEDFÖLJARE" layers, representing helper seats
        # behind wheelchair positions.
        if ("STOLAR" in layer and "MEDF" in layer.upper()
                and e.dxftype() == "LWPOLYLINE"):
            pts = list(e.get_points(format="xy"))
            if len(pts) >= 3:
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                sec = layer.split("-")[0] if "-" in layer else None
                if sec:
                    companion_polys.append(dict(
                        section=sec, x=cx, y=cy, handle=e.dxf.handle))

    return (seats, row_labels, wheelchair, section_letters, divider_lines,
            companion_polys)


# ---------------------------------------------------------------------------
# K-gap clustering
# ---------------------------------------------------------------------------

def _kgap_clusters(dists, k):
    """Split 1-D values into k clusters using the k-1 largest gaps."""
    n = len(dists)
    if n == 0 or k <= 0:
        return []
    order = np.argsort(dists).tolist()
    if k >= n:
        return [[idx] for idx in order]
    svals = np.array(dists)[order]
    gaps = np.diff(svals)
    splits = sorted(np.argsort(gaps)[::-1][:k - 1].tolist())
    clusters, start = [], 0
    for si in splits:
        clusters.append(order[start:si + 1])
        start = si + 1
    clusters.append(order[start:])
    return clusters


# ---------------------------------------------------------------------------
# Fan-sweep row assignment
# ---------------------------------------------------------------------------

def _count_within_dups(seats, assignments):
    """Count within-row duplicate seat numbers."""
    row_map = defaultdict(list)
    for s, rn in zip(seats, assignments):
        row_map[rn].append(s["text"])
    return sum(len(v) - len(set(v)) for v in row_map.values())


def _extract_label_rows(row_labels_for_section, cx, cy):
    """Parse row labels into (row_number, radial_distance) pairs.

    cx, cy is the center point (local center of curvature or global centroid).
    """
    result = []
    for lb in row_labels_for_section:
        txt = lb["text"].strip()
        if txt.lstrip("-").isdigit():
            row_num = int(txt)
            dist = math.hypot(lb["x"] - cx, lb["y"] - cy)
            result.append((row_num, dist))
    result.sort(key=lambda x: x[1])
    return result


def assign_rows_nearest_label(seats, label_rows, cx, cy):
    """Assign each seat to the nearest row label by radial distance.

    cx, cy is the center point (local center of curvature or global centroid).
    """
    if not label_rows:
        return None
    assignments = []
    for s in seats:
        d = math.hypot(s["x"] - cx, s["y"] - cy)
        best_row = min(label_rows, key=lambda lr: abs(lr[1] - d))[0]
        assignments.append(best_row)
    return assignments


def assign_rows_nearest_label_projected(seats, label_rows, gcx, gcy):
    """Assign rows by projecting seats onto the section's radial axis.

    Computes a unit vector from the arena centre through the section
    centroid.  Each seat's distance is measured as its projection onto
    that axis, compensating for curvature in non-circular arenas.
    Label radial distances are used directly (they are already
    measured from the centre).
    """
    if not label_rows:
        return None

    cx = float(np.mean([s["x"] for s in seats]))
    cy = float(np.mean([s["y"] for s in seats]))
    rd = math.hypot(cx - gcx, cy - gcy)
    if rd < 1:
        return None
    ux, uy = (cx - gcx) / rd, (cy - gcy) / rd

    assignments = []
    for s in seats:
        p = (s["x"] - gcx) * ux + (s["y"] - gcy) * uy
        best_row = min(label_rows, key=lambda lr: abs(lr[1] - p))[0]
        assignments.append(best_row)
    return assignments


def assign_rows_kgap(seats, cx, cy, min_row, max_row):
    """K-gap clustering on radial distance from (cx, cy).

    cx, cy can be the local center of curvature or the global centroid.
    Clusters are ordered by ascending mean distance (closest = min_row).
    """
    n = len(seats)
    k = max_row - min_row + 1
    if n == 0 or k <= 0 or k > n:
        return None

    dists = [math.hypot(s["x"] - cx, s["y"] - cy) for s in seats]
    clusters = _kgap_clusters(dists, k)
    if not clusters:
        return None

    cluster_order = sorted(
        clusters,
        key=lambda cl: float(np.mean([dists[i] for i in cl])))

    row_numbers = list(range(min_row, max_row + 1))
    assignments = [0] * n
    for rank, cl in enumerate(cluster_order):
        rn = row_numbers[min(rank, len(row_numbers) - 1)]
        for idx in cl:
            assignments[idx] = rn
    return assignments


def assign_rows_kgap_rotated(seats, text_rot_deg, gcx, gcy, min_row, max_row):
    """K-gap clustering on rotated-Y (using TEXT rotation angle)."""
    n = len(seats)
    k = max_row - min_row + 1
    if n == 0 or k <= 0 or k > n:
        return None

    a = math.radians(-text_rot_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)
    ry = [(s["x"] - gcx) * sin_a + (s["y"] - gcy) * cos_a for s in seats]

    clusters = _kgap_clusters(ry, k)
    if not clusters:
        return None

    cluster_order = sorted(
        clusters,
        key=lambda cl: float(np.mean([ry[i] for i in cl])))

    dists = [math.hypot(s["x"] - gcx, s["y"] - gcy) for s in seats]
    first_dist = float(np.mean([dists[i] for i in cluster_order[0]]))
    last_dist = float(np.mean([dists[i] for i in cluster_order[-1]]))
    if first_dist > last_dist:
        cluster_order.reverse()

    row_numbers = list(range(min_row, max_row + 1))
    assignments = [0] * n
    for rank, cl in enumerate(cluster_order):
        rn = row_numbers[min(rank, len(row_numbers) - 1)]
        for idx in cl:
            assignments[idx] = rn
    return assignments


def _try_cascade(assignments, seats, dists, row_map,
                 move_i, sn, from_rn, direction, clamp_range, depth=0):
    """Recursively move a duplicate seat to an adjacent row.

    If the target row already has that seat number, try to cascade-move
    the blocker further in the same direction (up to depth 8).
    """
    if depth > 8:
        return False
    target_rn = from_rn + direction
    if clamp_range and (target_rn < clamp_range[0]
                        or target_rn > clamp_range[1]):
        return False

    target_indices = row_map.get(target_rn, [])
    target_sns = {seats[j]["text"] for j in target_indices}

    if sn not in target_sns:
        assignments[move_i] = target_rn
        row_map[from_rn].remove(move_i)
        row_map.setdefault(target_rn, []).append(move_i)
        return True

    blockers = [j for j in target_indices if seats[j]["text"] == sn]
    if not blockers:
        return False

    target_med = (float(np.median([dists[j] for j in target_indices]))
                  if target_indices else 0)
    blocker = max(blockers, key=lambda j: abs(dists[j] - target_med))

    if _try_cascade(assignments, seats, dists, row_map,
                    blocker, sn, target_rn, direction, clamp_range,
                    depth + 1):
        assignments[move_i] = target_rn
        row_map[from_rn].remove(move_i)
        row_map[target_rn].append(move_i)
        return True
    return False


def _fix_row_duplicates(assignments, seats, dists, clamp_range=None):
    """Eliminate within-row duplicate seat numbers via cascade moves.

    Iteratively finds duplicate seat numbers within a row and tries to
    move the most borderline duplicate to an adjacent row (cascading
    through multiple rows if necessary).
    """
    assignments = list(assignments)

    for _ in range(200):
        row_map = defaultdict(list)
        for i, rn in enumerate(assignments):
            row_map[rn].append(i)

        moved = False
        for rn in sorted(row_map.keys()):
            indices = row_map[rn]
            sn_groups = defaultdict(list)
            for i in indices:
                sn_groups[seats[i]["text"]].append(i)

            for sn, group in sn_groups.items():
                if len(group) < 2:
                    continue

                row_med = float(np.median([dists[i] for i in indices]))
                group.sort(key=lambda i: abs(dists[i] - row_med),
                           reverse=True)

                move_i = group[0]
                d_i = dists[move_i]
                direction = 1 if d_i > row_med else -1

                if _try_cascade(assignments, seats, dists, row_map,
                                move_i, sn, rn, direction, clamp_range):
                    moved = True
                    break
                if _try_cascade(assignments, seats, dists, row_map,
                                move_i, sn, rn, -direction, clamp_range):
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break

    return assignments


def best_row_assignment(seats, candidates, cx, cy,
                        clamp_range=None):
    """Pick the assignment with fewest within-row duplicate seat numbers,
    then apply cascade duplicate fixing within clamp_range."""
    dists = [math.hypot(s["x"] - cx, s["y"] - cy) for s in seats]
    best = None
    best_dups = float("inf")
    best_name = ""
    for name, assignments in candidates:
        if assignments is None:
            continue
        fixed = _fix_row_duplicates(assignments, seats, dists, clamp_range)
        dups = _count_within_dups(seats, fixed)
        if dups < best_dups:
            best_dups = dups
            best = fixed
            best_name = name
        if dups == 0:
            break
    return best, best_dups, best_name


# ---------------------------------------------------------------------------
# Angular wedge helpers (Phase 1)
# ---------------------------------------------------------------------------

def _angle_from_center(x, y, gcx, gcy):
    return math.degrees(math.atan2(y - gcy, x - gcx)) % 360


def _angle_between(angle, lo, hi):
    """Is angle strictly between lo and hi going counter-clockwise?"""
    if lo < hi:
        return lo < angle < hi
    return angle > lo or angle < hi


def _is_radial_line(line, gcx, gcy):
    """Check if a SEKTIONER line is roughly radial (pointing toward/away
    from the arena centre)."""
    mx = (line["sx"] + line["ex"]) / 2
    my = (line["sy"] + line["ey"]) / 2
    mid_angle = _angle_from_center(mx, my, gcx, gcy)
    line_angle = math.degrees(
        math.atan2(line["ey"] - line["sy"], line["ex"] - line["sx"])) % 360

    diff1 = abs(line_angle - mid_angle) % 360
    if diff1 > 180:
        diff1 = 360 - diff1
    diff2 = abs((line_angle + 180) % 360 - mid_angle) % 360
    if diff2 > 180:
        diff2 = 360 - diff2
    return min(diff1, diff2) < 30


def _line_side(px, py, sx, sy, ex, ey):
    """Signed area test: positive = left of line from (sx,sy)->(ex,ey)."""
    return (ex - sx) * (py - sy) - (ey - sy) * (px - sx)


def load_tele_boundaries(boundaries_path, gcx, gcy):
    """Load manually verified TELE section boundaries.

    Returns (section_order, bd_lookup, angular_wedges).
      bd_lookup[(sec_a,sec_b)] has directed lines (inner→outer).
      angular_wedges is sorted [(angle, sec_ccw), ...] for coarse assignment.
    """
    with open(boundaries_path, encoding="utf-8") as f:
        data = json.load(f)

    section_order = data["section_order"]
    bd_lookup = {}
    angular_wedges = []

    for bd_data in data["boundaries"]:
        sec_a, sec_b = bd_data["between"]
        is_entrance = bd_data.get("main_entrance", False)

        directed_lines = {}
        inner_pts = []
        for ln in bd_data["lines"]:
            sx, sy = ln["from"]
            ex, ey = ln["to"]
            d_s = math.hypot(sx - gcx, sy - gcy)
            d_e = math.hypot(ex - gcx, ey - gcy)
            if d_s <= d_e:
                directed = (sx, sy, ex, ey)
                inner_pts.append((sx, sy))
            else:
                directed = (ex, ey, sx, sy)
                inner_pts.append((ex, ey))

            side = ln.get("side")
            if side:
                directed_lines[side] = directed
            else:
                directed_lines[sec_a] = directed
                directed_lines[sec_b] = directed

        bd_info = dict(is_entrance=is_entrance,
                       directed_lines=directed_lines)
        bd_lookup[(sec_a, sec_b)] = bd_info
        bd_lookup[(sec_b, sec_a)] = bd_info

        ix = sum(p[0] for p in inner_pts) / len(inner_pts)
        iy = sum(p[1] for p in inner_pts) / len(inner_pts)
        angle = _angle_from_center(ix, iy, gcx, gcy)

        idx_a = section_order.index(sec_a)
        idx_b = section_order.index(sec_b)
        sec_ccw = sec_b if (idx_b - idx_a) % len(section_order) == 1 \
            else sec_a
        angular_wedges.append((angle, sec_ccw))

    angular_wedges.sort(key=lambda x: x[0])
    return section_order, bd_lookup, angular_wedges


def assign_tele_sections_from_boundaries(tele_seats, section_order,
                                          bd_lookup, angular_wedges,
                                          gcx, gcy):
    """Assign TELE seat sections using angular wedges + half-plane refinement.

    1. Angular wedge from inner-endpoint angles → coarse section.
    2. Half-plane test on both boundary lines of the coarse section
       corrects seats near boundary lines.  Line direction is inner→outer;
       LEFT (positive cross) = CCW section, RIGHT (negative) = CW section.
    """
    n_w = len(angular_wedges)
    w_angles = [w[0] for w in angular_wedges]
    w_sections = {i: angular_wedges[i][1] for i in range(n_w)}

    n_sec = len(section_order)
    sec_idx = {s: i for i, s in enumerate(section_order)}

    def _get_line(sec, neighbor):
        bd = bd_lookup.get((sec, neighbor))
        if bd is None:
            return None
        dl = bd["directed_lines"]
        return dl.get(sec) or dl.get(neighbor)

    for s in tele_seats:
        px, py = s["x"], s["y"]
        seat_angle = _angle_from_center(px, py, gcx, gcy)

        coarse = None
        for i in range(n_w):
            lo = w_angles[i]
            hi = w_angles[(i + 1) % n_w]
            if _angle_between(seat_angle, lo, hi) or abs(seat_angle - lo) < 0.01:
                coarse = w_sections[i]
                break
        if coarse is None:
            continue

        si = sec_idx[coarse]
        cw_nbr = section_order[(si - 1) % n_sec]
        ccw_nbr = section_order[(si + 1) % n_sec]

        cw_line = _get_line(coarse, cw_nbr)
        ccw_line = _get_line(coarse, ccw_nbr)

        assigned = coarse

        if cw_line is not None:
            side = _line_side(px, py, *cw_line)
            if side < 0:
                assigned = cw_nbr

        if ccw_line is not None and assigned == coarse:
            side = _line_side(px, py, *ccw_line)
            if side > 0:
                assigned = ccw_nbr

        s["section"] = assigned


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def resolve_companion_seats(companion_polys, all_seat_texts):
    """Assign rotations to companion (MEDFÖLJARE) seats from the nearest
    regular seat text entity.  Returns a list of seat records with
    tier='companion' and sequential numbering per section."""
    results = []
    section_counters = defaultdict(int)
    for cp in companion_polys:
        best_dist = float("inf")
        best_rot = 0.0
        for s in all_seat_texts:
            d = math.hypot(s["x"] - cp["x"], s["y"] - cp["y"])
            if d < best_dist:
                best_dist = d
                best_rot = s["rotation"]
        section_counters[cp["section"]] += 1
        n = section_counters[cp["section"]]
        results.append(dict(
            id=f"{cp['section']}-COMP-{n}",
            section=cp["section"],
            row="COMP", seat_number=str(n),
            tier="companion",
            x=round(cp["x"], 2), y=round(cp["y"], 2),
            rotation=round(best_rot, 2),
            handle=cp.get("handle", "")))
    return results


def main():
    print(f"Reading DXF: {DXF_PATH}")
    seats, row_labels, wheelchair, section_letters, divider_lines, \
        companion_polys = parse_dxf(DXF_PATH)

    with open(OVERRIDES_PATH, encoding="utf-8") as f:
        section_overrides = {k: v for k, v in json.load(f).items()
                             if not k.startswith("_")}

    tele_sections = sorted(k for k, v in section_overrides.items()
                           if "lower" in v)

    gcx = float(np.mean([s["x"] for s in seats]))
    gcy = float(np.mean([s["y"] for s in seats]))
    print(f"  Seats: {len(seats)},  Row labels: {len(row_labels)},  "
          f"Wheelchair: {len(wheelchair)},  Companion: {len(companion_polys)}")
    print(f"  Arena centroid: ({gcx:.0f}, {gcy:.0f})")
    print(f"  TELE sections: {tele_sections}")
    print(f"  Section letters: {sorted(section_letters.keys())}")
    print(f"  SEKTIONER divider lines: {len(divider_lines)}")

    # ── Split seats into two independent pools ─────────────────────────
    tele_seats = [s for s in seats if _is_tele_tier(s["tier"])]
    upper_seats = [s for s in seats if not _is_tele_tier(s["tier"])]
    print(f"\n  Pool split: {len(tele_seats)} TELE, {len(upper_seats)} upper")

    # ── Estimate local center of curvature per section ─────────────────
    # Uses UPPER seats only — they have correct rotations and correct
    # section assignments.  The center is then shared with TELE seats
    # in the same section.
    upper_by_section = defaultdict(list)
    for s in upper_seats:
        upper_by_section[s["section"]].append(s)

    section_centers = {}
    for sec, sec_seats in upper_by_section.items():
        sign = _toward_center_sign(sec_seats, gcx, gcy)
        section_centers[sec] = estimate_center(sec_seats, sign)

    centers_found = sum(1 for v in section_centers.values() if v)
    print(f"  Local centers estimated: {centers_found} / "
          f"{len(section_centers)} sections (from upper seats)")

    # ==================================================================
    # PHASE 1 — TELE seats
    # ==================================================================
    print(f"\n{'='*70}")
    print(f" PHASE 1: TELE seats ({len(tele_seats)})")
    print(f"{'='*70}")

    # Load manually verified boundary lines
    section_order_bd, bd_lookup, angular_wedges = load_tele_boundaries(
        BOUNDARIES_PATH, gcx, gcy)
    print(f"  Loaded {len(angular_wedges)} boundary lines from "
          f"tele_boundaries.json")

    # Store original layer-name section, then reassign via boundaries
    for s in tele_seats:
        s["original_section"] = s["section"]

    assign_tele_sections_from_boundaries(
        tele_seats, section_order_bd, bd_lookup, angular_wedges, gcx, gcy)

    changed_count = sum(1 for s in tele_seats
                        if s["section"] != s["original_section"])
    print(f"  Sections reassigned: {changed_count} / {len(tele_seats)}")

    # Show wedge assignment breakdown per section
    wedge_breakdown = defaultdict(lambda: defaultdict(int))
    for s in tele_seats:
        wedge_breakdown[s["section"]][s["original_section"]] += 1
    print(f"\n  Wedge assignment (section <- original layers):")
    for sec in sorted(wedge_breakdown.keys()):
        origins = wedge_breakdown[sec]
        parts = []
        for orig, cnt in sorted(origins.items(), key=lambda x: -x[1]):
            if orig == sec:
                parts.append(f"{cnt} own")
            else:
                parts.append(f"{cnt} from {orig}")
        print(f"    {sec:>3s} ({sum(origins.values()):>3d}): {', '.join(parts)}")

    # Reassign row labels for TELE tier using the same boundary approach
    tele_labels = [lb for lb in row_labels if lb["tier"] == "lower"]
    assign_tele_sections_from_boundaries(
        tele_labels, section_order_bd, bd_lookup, angular_wedges, gcx, gcy)

    tele_label_map = defaultdict(list)
    for lb in tele_labels:
        tele_label_map[lb["section"]].append(lb)

    # Group TELE seats by section and assign rows
    tele_groups = defaultdict(list)
    for s in tele_seats:
        tele_groups[s["section"]].append(s)

    tele_results = []
    tele_quality = {}

    for section in sorted(tele_groups.keys()):
        group = tele_groups[section]
        sec_info = section_letters.get(section)
        center = section_centers.get(section)
        ov = section_overrides.get(section, {}).get("lower", {})
        min_row = ov.get("min_row", 0)
        max_row = ov.get("max_row", 5)

        all_tele_labels = tele_label_map.get(section, [])

        # Use local center if available, otherwise global centroid
        cx, cy = center if center else (gcx, gcy)

        label_rows = _extract_label_rows(all_tele_labels, cx, cy)

        # Try multiple methods, pick best (zero within-row dups = correct)
        candidates = [
            ("kgap_local",
             assign_rows_kgap(group, cx, cy, min_row, max_row)),
            ("nearest_label",
             assign_rows_nearest_label(group, label_rows, cx, cy)),
        ]
        # Also try global centroid as fallback
        if center:
            candidates.append((
                "kgap_global",
                assign_rows_kgap(group, gcx, gcy, min_row, max_row)))
        if sec_info:
            candidates.append((
                "kgap_textrot",
                assign_rows_kgap_rotated(
                    group, sec_info["rotation"], gcx, gcy,
                    min_row, max_row)))

        assignments, within_dups, method = best_row_assignment(
            group, candidates, cx, cy,
            clamp_range=(min_row, max_row))

        if assignments is None:
            assignments = list(range(len(group)))
            within_dups = _count_within_dups(group, assignments)
            method = "sequential"

        found_rows = sorted(set(assignments))
        tele_quality[section] = dict(
            seats=len(group), rows=len(found_rows),
            range=f"{found_rows[0]}-{found_rows[-1]}",
            within_dups=within_dups, method=method)

        for seat, rn in zip(group, assignments):
            rec = dict(
                id=f"{section}-{rn}-{seat['text']}",
                section=section,
                row=int(rn), seat_number=seat["text"],
                tier=seat["tier"], x=round(seat["x"], 2),
                y=round(seat["y"], 2),
                rotation=round(seat["rotation"], 2),
                handle=seat.get("handle", ""))
            orig = seat.get("original_section", "")
            if orig and orig != section:
                rec["original_section"] = orig
            tele_results.append(rec)

    print(f"\n  {'Section':<10s} {'Seats':>6s} {'Rows':>5s} {'Range':8s} "
          f"{'WDup':>5s} {'Method':<16s}")
    print(f"  {'-'*55}")
    for sec in sorted(tele_quality.keys()):
        q = tele_quality[sec]
        print(f"  {sec:<10s} {q['seats']:>6d} {q['rows']:>5d} {q['range']:<8s} "
              f"{q['within_dups']:>5d} {q['method']:<16s}")
    total_tele_dups = sum(q["within_dups"] for q in tele_quality.values())
    print(f"  Total TELE within-row dups: {total_tele_dups}")

    # ==================================================================
    # PHASE 2 — Upper seats
    # ==================================================================
    print(f"\n{'='*70}")
    print(f" PHASE 2: Upper seats ({len(upper_seats)})")
    print(f"{'='*70}")

    upper_groups = defaultdict(list)
    for s in upper_seats:
        upper_groups[s["section"]].append(s)

    upper_results = []
    upper_quality = {}

    for section in sorted(upper_groups.keys()):
        group = upper_groups[section]
        sec_info = section_letters.get(section)
        center = section_centers.get(section)
        ov = section_overrides.get(section, {}).get("upper", {})
        min_row = ov.get("min_row")
        max_row = ov.get("max_row")

        # Use local center if available, otherwise global centroid
        cx, cy = center if center else (gcx, gcy)

        upper_labels = [lb for lb in row_labels
                        if lb["section"] == section and lb["tier"] == "upper"]
        label_rows = _extract_label_rows(upper_labels, cx, cy)

        candidates = [
            ("nearest_label",
             assign_rows_nearest_label(group, label_rows, cx, cy)),
        ]
        if min_row is not None and max_row is not None:
            candidates.append((
                "kgap_local",
                assign_rows_kgap(group, cx, cy, min_row, max_row)))
            if center:
                candidates.append((
                    "kgap_global",
                    assign_rows_kgap(group, gcx, gcy, min_row, max_row)))
            if sec_info:
                candidates.append((
                    "kgap_textrot",
                    assign_rows_kgap_rotated(
                        group, sec_info["rotation"], gcx, gcy,
                        min_row, max_row)))

        clamp = (min_row, max_row) if (min_row is not None
                                       and max_row is not None) else None
        assignments, within_dups, method = best_row_assignment(
            group, candidates, cx, cy, clamp_range=clamp)

        if assignments is None:
            assignments = list(range(len(group)))
            within_dups = _count_within_dups(group, assignments)
            method = "sequential"

        found_rows = sorted(set(assignments))
        upper_quality[(section, group[0]["tier"])] = dict(
            seats=len(group), rows=len(found_rows),
            range=f"{found_rows[0]}-{found_rows[-1]}",
            within_dups=within_dups, method=method)

        for seat, rn in zip(group, assignments):
            upper_results.append(dict(
                id=f"{section}-{rn}-{seat['text']}",
                section=section,
                row=int(rn), seat_number=seat["text"],
                tier=seat["tier"], x=round(seat["x"], 2),
                y=round(seat["y"], 2),
                rotation=round(seat["rotation"], 2),
                handle=seat.get("handle", "")))

    print(f"\n  {'Group':<12s} {'Seats':>6s} {'Rows':>5s} {'Range':8s} "
          f"{'WDup':>5s} {'Method':<11s}")
    print(f"  {'-'*55}")
    for key in sorted(upper_quality.keys()):
        sec, tier = key
        q = upper_quality[key]
        label = f"{sec}-{tier}"
        print(f"  {label:<12s} {q['seats']:>6d} {q['rows']:>5d} "
              f"{q['range']:<8s} {q['within_dups']:>5d} {q['method']:<11s}")
    total_upper_dups = sum(q["within_dups"] for q in upper_quality.values())
    print(f"  Total upper within-row dups: {total_upper_dups}")

    # Apply per-seat overrides from section_overrides.json
    for sec_name, sec_data in section_overrides.items():
        for tier_key in ("lower", "upper"):
            overrides = sec_data.get(tier_key, {}).get("seat_overrides", [])
            for ov in overrides:
                sn = ov["seat_number"]
                fr = ov["from_row"]
                tr = ov.get("to_row", fr)
                new_sn = ov.get("to_seat_number", sn)
                ov_handle = ov.get("handle")
                target = tele_results if tier_key == "lower" else upper_results
                for r in target:
                    if ov_handle:
                        if r.get("handle", "").upper() != ov_handle.upper():
                            continue
                    else:
                        if not (r["section"] == sec_name
                                and r["seat_number"] == sn
                                and r["row"] == fr):
                            continue
                    old_id = r["id"]
                    r["row"] = tr
                    r["seat_number"] = new_sn
                    r["id"] = f"{sec_name}-{tr}-{new_sn}"
                    print(f"  Override: {old_id} -> {r['id']}")

    # ==================================================================
    # Merge and output
    # ==================================================================
    wc_results = [dict(
        id=f"{ws['section']}-WC-{ws['text']}",
        section=ws["section"], row="WC", seat_number=ws["text"],
        tier="wheelchair", x=round(ws["x"], 2), y=round(ws["y"], 2),
        rotation=round(ws["rotation"], 2)) for ws in wheelchair]

    comp_results = resolve_companion_seats(companion_polys, seats)

    results = tele_results + upper_results + wc_results + comp_results

    # Summary
    total_seats = len(tele_results) + len(upper_results)
    unique_ids = set(r["id"] for r in results)
    duplicates = len(results) - len(unique_ids)

    print(f"\n{'='*70}")
    print(f" SUMMARY")
    print(f"{'='*70}")
    print(f"  TELE seats:  {len(tele_results)}")
    print(f"  Upper seats: {len(upper_results)}")
    print(f"  Wheelchair:  {len(wc_results)}")
    print(f"  Companion:   {len(comp_results)}")
    print(f"  Total:       {len(results)}")
    print(f"  Unique IDs:  {len(unique_ids)}")

    if duplicates:
        print(f"  Duplicate IDs: {duplicates}")
        id_counts = Counter(r["id"] for r in results)
        dups = [(k, v) for k, v in id_counts.items() if v > 1]
        sec_dup = defaultdict(int)
        for did, cnt in dups:
            sec_dup[did.split("-")[0]] += cnt - 1
        for sec in sorted(sec_dup):
            print(f"    Section {sec}: {sec_dup[sec]} extra")
        for did, cnt in sorted(dups)[:10]:
            print(f"    {did}: {cnt}x")
        if len(dups) > 10:
            print(f"    ... and {len(dups) - 10} more")
    else:
        print("  No duplicate IDs!")

    # ==================================================================
    # Apply row heights from row_heights.json
    # ==================================================================
    if os.path.isfile(ROW_HEIGHTS_PATH):
        with open(ROW_HEIGHTS_PATH, encoding="utf-8") as f:
            row_heights = json.load(f)
        row_heights.pop("_comment", None)
        applied = 0
        for r in results:
            row_key = str(r.get("row", ""))
            if row_key in row_heights:
                r["z"] = row_heights[row_key]
                applied += 1
            else:
                r["z"] = 0.0
        print(f"  Applied Z heights to {applied}/{len(results)} seats "
              f"from {os.path.basename(ROW_HEIGHTS_PATH)}")
    else:
        print(f"  WARNING: {ROW_HEIGHTS_PATH} not found, z values not set")

    # Seat mesh vs CAD label offset is applied in generate_instancer.py only;
    # this JSON stays raw CAD (navigation uses these coordinates).

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
