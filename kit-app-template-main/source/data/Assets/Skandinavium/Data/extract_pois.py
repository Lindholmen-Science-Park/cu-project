"""Extract categorised Points-Of-Interest from the Skandinavium DXF text labels.

Reads ``all_texts.json`` (produced by ``analyze_dxf.py``) and turns every
human-readable room label into a typed POI entry.

Outputs (next to this script):
  * ``pois.json`` - structured JSON with metadata, categories and POI list
  * ``pois.csv``  - flat CSV (Excel-friendly) for quick inspection

Coordinates are kept in **DXF millimetres** (the drawing's native units) and
are NOT transformed into any world / USD coordinate frame.  Wiring this into
the runtime POI pipeline is intentionally out of scope.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


HERE = Path(__file__).parent
TEXTS_PATH = HERE / "all_texts.json"
POIS_JSON_PATH = HERE / "pois.json"
POIS_CSV_PATH = HERE / "pois.csv"


# --------------------------------------------------------------------------- #
# Classification rules
# --------------------------------------------------------------------------- #
# Each rule is (category, description, list of (regex, priority)).
# The first matching rule wins; within a rule, regexes are tried in order.
# Regexes are evaluated against the upper-cased, whitespace-collapsed label.
# Word boundaries are added implicitly via the helper below.

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "restroom_wheelchair":  "Wheelchair-accessible toilet (RWC)",
    "restroom_accessible":  "Accessible / handicap toilet (HWC)",
    "restroom_women":       "Women's toilet (DAMTOALETT)",
    "restroom_men":         "Men's toilet (HERRTOALETT)",
    "restroom_generic":     "Toilet, unspecified gender (WC / TOALETT)",
    "restroom_anteroom":    "Toilet ante-room (FÖRRUM WC)",
    "entrance_stand":       "Spectator stand entrance (LÄKTARENTRÉ X)",
    "entrance_main":        "Main / guest / congress entrance",
    "entrance_hall":        "Entrance hall / foyer (ENTRÉHALL)",
    "elevator":             "Elevator (HISS)",
    "stair":                "Staircase (TRAPPA / TRAPPHALL)",
    "kitchen":              "Kitchen (KÖK)",
    "office":               "Office (KONTOR)",
    "storage":              "Storage room (FÖRRÅD)",
    "medical":              "Medical / first-aid room (SJUKVÅRDSRUM)",
    "hall":                 "Generic hall / passage (HALL, PASSAGE)",
    "technical":            "Technical room (VVS, ELC., MHD)",
    "bar":                  "Bar / serving area",
    "kiosk":                "Kiosk",
    "locker":               "Locker / changing room (OMKLÄDN, LOGE, DUSCH)",
}


def _word(pattern: str) -> re.Pattern:
    """Build a regex that matches PATTERN as a whole word (Swedish letters)."""
    return re.compile(rf"(?<![A-ZÅÄÖ]){pattern}(?![A-ZÅÄÖ])")


# Order matters: more specific rules first.
RULES: list[tuple[str, list[re.Pattern]]] = [
    ("restroom_wheelchair", [_word(r"RWC")]),
    ("restroom_accessible", [_word(r"HWC")]),
    ("restroom_anteroom",   [re.compile(r"FÖRRUM\s+WC")]),
    ("restroom_women",      [_word(r"DAMTOALETT"), _word(r"DAM\s*WC"),
                             _word(r"DAMER")]),
    ("restroom_men",        [_word(r"HERRTOALETT"), _word(r"HERR\s*WC"),
                             _word(r"HERRAR")]),
    ("restroom_generic",    [_word(r"WC"), _word(r"TOALETT")]),
    ("entrance_stand",      [re.compile(r"LÄKTARENTRÉ")]),
    ("entrance_hall",       [re.compile(r"ENTRÉHALL"),
                             re.compile(r"ENTRÈHALL"),
                             re.compile(r"ENTRÉH\.")]),
    ("entrance_main",       [re.compile(r"GÄSTENTRÉ"),
                             re.compile(r"KONGRESSENTRÉ"),
                             _word(r"ENTRÉ"), _word(r"INGÅNG")]),
    ("elevator",            [_word(r"HISSM\.?"), _word(r"HISS")]),
    ("stair",               [_word(r"TRAPPHALL"), _word(r"TRAPPA"),
                             _word(r"TRAPP")]),
    ("kitchen",             [_word(r"KÖK"), _word(r"PENTRY")]),
    ("office",              [_word(r"KONTOR")]),
    ("storage",             [_word(r"FÖRRÅD")]),
    ("medical",             [_word(r"SJUKVÅRDSRUM"),
                             _word(r"FÖRSTA\s+HJÄLP")]),
    ("hall",                [_word(r"HALL"), _word(r"FOAJÉ"),
                             _word(r"PASSAGE")]),
    ("technical",           [_word(r"VVS"), _word(r"ELC\.?"),
                             _word(r"MHD"), _word(r"FLÄKTRUM"),
                             _word(r"TEKNIK")]),
    ("bar",                 [_word(r"BAR"), _word(r"BARDISK")]),
    ("kiosk",               [_word(r"KIOSK")]),
    ("locker",              [_word(r"OMKLÄDN"), _word(r"OMKL"),
                             _word(r"LOGE"), _word(r"DUSCH")]),
]


def classify(text: str) -> Optional[str]:
    """Return the POI category for a label, or None if it isn't a room name."""
    if not text:
        return None
    norm = re.sub(r"\s+", " ", text.strip().upper())
    for category, patterns in RULES:
        for pat in patterns:
            if pat.search(norm):
                return category
    return None


# --------------------------------------------------------------------------- #
# Plan-copy detection
# --------------------------------------------------------------------------- #
# The DXF contains the same floor plan twice: the main copy roughly inside
# x in [-110_000, 80_000] and a second annotated copy starting around
# x ~= 145_000 (offset ~270 m east). We tag each POI with which copy it
# belongs to so callers can filter to a single view.

PLAN_COPY_THRESHOLD_X = 100_000.0  # mm, midpoint between the two copies


def plan_copy_for(x: float) -> str:
    return "main" if x < PLAN_COPY_THRESHOLD_X else "duplicate"


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Poi:
    id: str
    category: str
    label: str            # cleaned, single-line
    raw_text: str         # original text (may contain newlines / markup)
    dxf_layer: str
    dxf_x_mm: float
    dxf_y_mm: float
    text_height_mm: float
    plan_copy: str        # "main" or "duplicate"
    source_entity: str    # "TEXT", "MTEXT" or "ATTRIB"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    # all_texts.json was written by analyze_dxf.py without an explicit
    # encoding, so on Windows it ends up cp1252. Try utf-8 first, fall back
    # to cp1252 to stay tolerant.
    try:
        raw_texts = json.loads(TEXTS_PATH.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raw_texts = json.loads(TEXTS_PATH.read_text(encoding="cp1252"))
    print(f"Loaded {len(raw_texts)} text entries from {TEXTS_PATH.name}")

    pois: list[Poi] = []
    seen_ids: Counter = Counter()
    skipped_examples: list[str] = []

    for entry in raw_texts:
        body = (entry.get("text") or "").strip()
        if not body:
            continue
        category = classify(body)
        if not category:
            if len(skipped_examples) < 20 and len(body) <= 40:
                skipped_examples.append(body)
            continue

        cleaned = re.sub(r"\s+", " ", body).strip()
        x = float(entry["x"])
        y = float(entry["y"])
        copy = plan_copy_for(x)

        seen_ids[category] += 1
        poi = Poi(
            id=f"{category}_{copy}_{seen_ids[category]:03d}",
            category=category,
            label=cleaned,
            raw_text=body,
            dxf_layer=entry.get("layer", ""),
            dxf_x_mm=round(x, 2),
            dxf_y_mm=round(y, 2),
            text_height_mm=round(float(entry.get("height", 0.0)), 2),
            plan_copy=copy,
            source_entity=entry.get("type", "MTEXT"),
        )
        pois.append(poi)

    # ----- summarise ------------------------------------------------------- #
    by_cat: Counter = Counter(p.category for p in pois)
    by_cat_main: Counter = Counter(
        p.category for p in pois if p.plan_copy == "main"
    )

    print("\nExtracted POIs by category:")
    print(f"  {'category':22} {'total':>6} {'main-copy':>10}")
    for cat, total in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:22} {total:>6} {by_cat_main.get(cat, 0):>10}")
    print(f"  {'TOTAL':22} {sum(by_cat.values()):>6} "
          f"{sum(by_cat_main.values()):>10}")

    # ----- write JSON ------------------------------------------------------ #
    payload = {
        "source": {
            "file": "A-40_P0010.dxf",
            "title": "Skandinavium ground floor (PLAN 1, 2018)",
            "units": "millimeters",
            "coordinate_system": "DXF model space (untransformed)",
            "notes": [
                "Coordinates are raw DXF mm; no rotation/translation has "
                "been applied to align with the USD/world frame.",
                "The drawing contains two copies of the same floor plan "
                "side by side. Filter by `plan_copy == 'main'` to keep "
                "only one set of room labels.",
                "Categories are derived from Swedish room name heuristics; "
                "review before relying on them for safety-critical use.",
            ],
        },
        "categories": CATEGORY_DESCRIPTIONS,
        "summary": {
            "total": sum(by_cat.values()),
            "by_category": dict(by_cat),
            "by_category_main_copy_only": dict(by_cat_main),
        },
        "pois": [asdict(p) for p in pois],
    }
    POIS_JSON_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ----- write CSV ------------------------------------------------------- #
    with POIS_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow([
            "id", "category", "label", "plan_copy",
            "dxf_x_mm", "dxf_y_mm", "dxf_layer",
            "text_height_mm", "source_entity", "raw_text",
        ])
        for p in pois:
            writer.writerow([
                p.id, p.category, p.label, p.plan_copy,
                p.dxf_x_mm, p.dxf_y_mm, p.dxf_layer,
                p.text_height_mm, p.source_entity,
                p.raw_text.replace("\n", " | "),
            ])

    print(f"\nWrote {POIS_JSON_PATH.name} and {POIS_CSV_PATH.name}")
    if skipped_examples:
        print("\nFirst few unclassified labels (for tuning the rules):")
        for s in skipped_examples:
            print(f"  - {s!r}")


if __name__ == "__main__":
    main()
