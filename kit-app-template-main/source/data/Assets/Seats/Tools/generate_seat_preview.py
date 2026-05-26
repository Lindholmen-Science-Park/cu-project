"""Generate a USDA preview of extracted DXF seats for visual verification.

Each seat is a small flat Cube prim named by its ID (e.g. A_5_10).
Colour-coded by tier. DXF mm coordinates used directly (metersPerUnit=0.001).

Usage:  python generate_seat_preview.py
"""

import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEATS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SEATS_DIR, "Data")
INPUT_JSON = os.path.join(DATA_DIR, "extracted_seats_with_rows.json")
OUTPUT_USDA = os.path.join(SEATS_DIR, "seats_preview.usda")

TIER_COLORS = {
    "lower":       "(0, 0.7, 0.15)",
    "lower2":      "(0, 0.4, 0.9)",
    "extra_lower": "(0.9, 0.75, 0)",
    "upper":       "(0.85, 0.12, 0.1)",
    "wheelchair":  "(0.7, 0.2, 0.8)",
}

CUBE_HALF = 150
CUBE_HEIGHT = 40


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def main():
    with open(INPUT_JSON, encoding="utf-8") as f:
        seats = json.load(f)
    print(f"Loaded {len(seats)} seats")

    # Deduplicate prim names — USD requires unique sibling names
    seen = {}
    for s in seats:
        pn = sanitize(s["id"])
        sec = sanitize(s.get("section", s["id"].split("-")[0]))
        key = (sec, pn)
        if key in seen:
            seen[key] += 1
            s["_prim"] = f"{pn}_d{seen[key]}"
        else:
            seen[key] = 0
            s["_prim"] = pn

    sections = {}
    for s in seats:
        sec = sanitize(s.get("section", s["id"].split("-")[0]))
        sections.setdefault(sec, []).append(s)

    with open(OUTPUT_USDA, "w", encoding="utf-8") as out:
        out.write('#usda 1.0\n')
        out.write('(\n')
        out.write('    defaultPrim = "Seats"\n')
        out.write('    metersPerUnit = 0.001\n')
        out.write('    upAxis = "Z"\n')
        out.write(')\n\n')
        out.write('def Xform "Seats"\n{\n')

        for sec_name in sorted(sections):
            sec_seats = sections[sec_name]
            out.write(f'\n    def Xform "{sec_name}"\n')
            out.write('    {\n')

            for s in sec_seats:
                prim_name = s["_prim"]
                x = s["x"]
                y = s["y"]
                rot = s.get("rotation", 0.0)
                tier = s.get("tier", "upper")
                color = TIER_COLORS.get(tier, "(0.5, 0.5, 0.5)")

                out.write(f'        def Cube "{prim_name}"\n')
                out.write('        {\n')
                out.write(f'            double3 xformOp:translate = ({x}, {y}, 0)\n')
                out.write(f'            double xformOp:rotateZ = {rot}\n')
                out.write(f'            float3 xformOp:scale = ({CUBE_HALF}, {CUBE_HALF}, {CUBE_HEIGHT})\n')
                out.write('            uniform token[] xformOpOrder = '
                          '["xformOp:translate", "xformOp:rotateZ", "xformOp:scale"]\n')
                out.write(f'            color3f[] primvars:displayColor = [{color}]\n')
                out.write('        }\n')

            out.write('    }\n')

        out.write('}\n')

    size_mb = os.path.getsize(OUTPUT_USDA) / (1024 * 1024)
    print(f"Wrote {OUTPUT_USDA}  ({size_mb:.1f} MB, {len(seats)} prims)")


if __name__ == "__main__":
    main()
