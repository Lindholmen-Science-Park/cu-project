"""Strip tier visual pivots from seat JSON (restore raw CAD).

Run **once** when migrating from in-JSON offsets to instancer-only correction.
Do **not** run on JSON that is already CAD-true (would shift coordinates wrong).

After stripping, regenerate:
  python generate_instancer.py && python create_lookup.py

Usage (from this directory):
    python apply_seat_pivot_to_data_jsons.py
"""

import json
import os

from seat_pivot_offset import strip_visual_pivot_from_seat_json_records

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "Data"))

BASELINE = os.path.join(DATA_DIR, "extracted_seats_with_rows.json")
EVENT = os.path.join(DATA_DIR, "extracted_event_seats.json")


def main():
    for path in (BASELINE, EVENT):
        if not os.path.isfile(path):
            print(f"Skip (missing): {path}")
            continue
        with open(path, encoding="utf-8") as f:
            seats = json.load(f)
        n = strip_visual_pivot_from_seat_json_records(seats)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(seats, f, indent=2, ensure_ascii=False)
        print(f"Stripped visual pivot from {os.path.basename(path)}: {n} records")


if __name__ == "__main__":
    main()
