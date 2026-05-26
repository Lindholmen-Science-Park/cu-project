"""Build a compact section/row/seat hierarchy for the web seat-finder dropdowns.

Reads ``Data/extracted_seats_with_rows.json`` (master seat list) and writes a
small JSON file consumed directly by the React frontend so the Section / Row /
Seat dropdowns can cascade dynamically (Section -> only valid Rows for that
section -> only valid Seats for that section+row).

Output structure::

    {
      "walking": {
        "A": { "1": ["1", "2", ...], "2": [...], ... },
        ...
      },
      "wheelchair": {
        "C": { "6": ["1", "2", "3", "4", "5", "6"] },
        "D": { "6": ["1", "2", "3", "4"] },
        ...
      }
    }

``wheelchair`` mirrors ``walking``: section → row key (ticket row, e.g. ``6``)
→ seat numbers. Legacy CAD rows may still use ``WC`` with ``R`` seat labels
until ``postprocess_wheelchair_wc_to_row6.py`` is applied.

Companion (MEDFOLJARE) seats are excluded -- they are visual-only and not
navigable.

Output is written to the frontend so Vite can ``import`` it directly:
``web-viewer-sample-main/src/features/streaming/widgets/seat-navigate/data/
seat_hierarchy.json``.

Run after ``extract_cad_seats.py`` (it reads the same source file).  The full
``rebuild_seats.py`` pipeline runs this as step 4 but does **not** run
``postprocess_wheelchair_wc_to_row6.py`` — apply that step after extraction when
needed (see ``.cursor/rules/topics/seat-navigation.mdc`` § Step 1a).
"""

import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEATS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SEATS_DIR, "Data")
SEATS_JSON = os.path.join(DATA_DIR, "extracted_seats_with_rows.json")

REPO_ROOT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "..", "..", "..", ".."))
FRONTEND_OUTPUT = os.path.normpath(os.path.join(
    REPO_ROOT,
    "web-viewer-sample-main", "src", "features", "streaming", "widgets",
    "seat-navigate", "data", "seat_hierarchy.json",
))

_DIGIT_RE = re.compile(r"^\d+$")
_R_PREFIX_RE = re.compile(r"^[Rr](\d+)$")


def _seat_sort_key(value):
    """Sort numerically when possible; fall back to lexicographic for stability."""
    if _DIGIT_RE.match(value):
        return (0, int(value), value)
    return (1, 0, value)


def _normalize_wheelchair_seat(seat_number):
    """Strip the internal ``R`` prefix so the UI sees plain digits."""
    if seat_number is None:
        return ""
    raw = str(seat_number).strip()
    m = _R_PREFIX_RE.match(raw)
    return m.group(1) if m else raw


def _build_walking(seats):
    """section -> { row(str) -> sorted unique seat numbers }."""
    out = {}
    for s in seats:
        if s.get("tier") in ("wheelchair", "companion"):
            continue
        section = str(s.get("section") or "").strip().upper()
        if not section:
            continue
        row = str(s.get("row")).strip() if s.get("row") is not None else ""
        if not row:
            continue
        seat_no = str(s.get("seat_number") or "").strip()
        if not seat_no:
            continue
        out.setdefault(section, {}).setdefault(row, set()).add(seat_no)

    result = {}
    for section in sorted(out.keys()):
        rows = out[section]
        sorted_rows = {}
        for row in sorted(rows.keys(), key=_seat_sort_key):
            sorted_rows[row] = sorted(rows[row], key=_seat_sort_key)
        result[section] = sorted_rows
    return result


def _build_wheelchair(seats):
    """section -> { row -> sorted unique seat numbers } (ticket-style)."""
    out = {}
    for s in seats:
        if s.get("tier") != "wheelchair":
            continue
        section = str(s.get("section") or "").strip().upper()
        row = str(s.get("row")).strip() if s.get("row") is not None else ""
        seat_no = _normalize_wheelchair_seat(s.get("seat_number"))
        if not section or not row or not seat_no:
            continue
        out.setdefault(section, {}).setdefault(row, set()).add(seat_no)

    result = {}
    for section in sorted(out.keys()):
        rows = out[section]
        sorted_rows = {}
        for row in sorted(rows.keys(), key=_seat_sort_key):
            sorted_rows[row] = sorted(rows[row], key=_seat_sort_key)
        result[section] = sorted_rows
    return result


def main():
    print(f"Reading {SEATS_JSON}")
    with open(SEATS_JSON, encoding="utf-8") as f:
        seats = json.load(f)
    print(f"  Loaded {len(seats)} seats")

    walking = _build_walking(seats)
    wheelchair = _build_wheelchair(seats)

    walking_seat_total = sum(
        len(seats_in_row)
        for rows in walking.values()
        for seats_in_row in rows.values()
    )
    wheelchair_seat_total = sum(
        len(seats_in_row)
        for rows in wheelchair.values()
        for seats_in_row in rows.values()
    )
    print(
        f"  walking: {len(walking)} sections, "
        f"{sum(len(r) for r in walking.values())} rows, "
        f"{walking_seat_total} seats"
    )
    print(
        f"  wheelchair: {len(wheelchair)} sections, "
        f"{sum(len(r) for r in wheelchair.values())} rows, "
        f"{wheelchair_seat_total} seats"
    )

    payload = {"walking": walking, "wheelchair": wheelchair}
    os.makedirs(os.path.dirname(FRONTEND_OUTPUT), exist_ok=True)
    with open(FRONTEND_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))

    size_kb = os.path.getsize(FRONTEND_OUTPUT) / 1024
    print(f"\nWrote {FRONTEND_OUTPUT}")
    print(f"  {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
