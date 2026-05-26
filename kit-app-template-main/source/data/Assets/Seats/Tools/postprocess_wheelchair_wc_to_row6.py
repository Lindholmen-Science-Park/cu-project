"""Post-process CAD wheelchair rows into ticket-style row 6 + numeric seat.

Run from ``Tools/`` after ``extract_cad_seats.py`` (or whenever the master JSON
still has legacy wheelchair rows)::

    python postprocess_wheelchair_wc_to_row6.py

For every seat with ``"row": "WC"``:

- ``row`` -> ``"6"``
- ``seat_number`` ``"R14"`` / ``"r14"`` -> ``"14"`` (leading ``R`` stripped)
- ``id`` ``"G-WC-R14"`` -> ``"G-6-14"`` (``{section}-6-{number}``)

``section`` is normalised to uppercase. Other fields (``x``, ``y``, ``z``,
``tier``, etc.) are left unchanged.

Files updated (same directory as ``extract_cad_seats`` output):

- ``Data/extracted_seats_with_rows.json``
- ``Data/extracted_event_seats.json`` (if present)

Idempotent: seats whose ``row`` is already ``"6"`` are skipped.

**Note:** In sections where numeric row ``6`` already has regular seats (e.g.
some upper-tier layouts), this id pattern can collide with walking seats.
This script applies the mapping you asked for; resolve clashes in CAD or
overrides if they appear.

Then re-run ``generate_instancer.py``, ``create_lookup.py``, and
``build_seat_hierarchy.py`` (or ``rebuild_seats.py``) so USD, availability,
lookup, and web hierarchy stay in sync.
"""

from __future__ import annotations

import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "Data"))
PATHS = [
    os.path.join(DATA_DIR, "extracted_seats_with_rows.json"),
    os.path.join(DATA_DIR, "extracted_event_seats.json"),
]

_R_SEAT = re.compile(r"^[Rr](\d+)$")


def _transform_wc_seat(seat: dict) -> bool:
    """Return True if this dict was updated."""
    if str(seat.get("row", "")) != "WC":
        return False
    raw_sn = str(seat.get("seat_number", "")).strip()
    m = _R_SEAT.match(raw_sn)
    if not m:
        print(f"  WARN: WC seat without R-prefixed seat_number: id={seat.get('id')!r} seat_number={raw_sn!r}")
        return False
    digits = m.group(1)
    sn_out = str(int(digits, 10))
    sec = str(seat.get("section", "")).strip().upper()
    if not sec:
        print(f"  WARN: WC seat missing section: id={seat.get('id')!r}")
        return False
    seat["section"] = sec
    seat["row"] = "6"
    seat["seat_number"] = sn_out
    seat["id"] = f"{sec}-6-{sn_out}"
    return True


def _process_file(path: str) -> int:
    if not os.path.isfile(path):
        print(f"  Skip (missing): {path}")
        return 0
    with open(path, encoding="utf-8") as f:
        seats = json.load(f)
    n = 0
    for s in seats:
        if _transform_wc_seat(s):
            n += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seats, f, indent=2, ensure_ascii=False)
    print(f"  Updated {n} WC -> row-6 seats in {path}")
    return n


def main() -> None:
    total = 0
    for p in PATHS:
        print(os.path.basename(p))
        total += _process_file(p)
    print(f"\nTotal wheelchair rows rewritten: {total}")


if __name__ == "__main__":
    main()
