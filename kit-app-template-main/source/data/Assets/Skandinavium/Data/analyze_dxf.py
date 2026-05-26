"""Quick analysis of the Skandinavium DXF floorplan.

Outputs a text report describing:
  * file metadata + drawing extents
  * layers (with usage counts)
  * block definitions (counted)
  * entity counts by type
  * all text labels (TEXT / MTEXT / ATTRIB) with their layer + position
  * heuristic search for restroom / WC / facility-related labels
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf
from ezdxf import bbox

DXF_PATH = Path(__file__).with_name("A-40_P0010.dxf")
OUT_DIR = Path(__file__).parent
REPORT_PATH = OUT_DIR / "analysis_report.txt"
TEXTS_JSON_PATH = OUT_DIR / "all_texts.json"
LAYERS_JSON_PATH = OUT_DIR / "layers.json"


FACILITY_KEYWORDS = [
    # english
    "wc", "toilet", "restroom", "bathroom", "lavatory",
    "men", "women", "ladies", "gents",
    "kitchen", "office", "storage", "elevator", "lift", "stair",
    "exit", "entrance", "lobby", "foyer",
    "first aid", "medical",
    # swedish (Skandinavium is in Gothenburg)
    "wc", "toa", "toalett", "rwc", "hwc",
    "damm", "herr",
    "kök", "kontor", "förråd", "hiss", "trapp",
    "utgång", "entré", "ingång",
    "första hjälp", "läkare", "sjuk",
    "loge", "omkläd", "dusch",
]


def main() -> None:
    print(f"Loading {DXF_PATH.name} ({DXF_PATH.stat().st_size/1024/1024:.1f} MB) ...")
    doc = ezdxf.readfile(str(DXF_PATH))
    msp = doc.modelspace()

    # ---- header / extents -------------------------------------------------
    header = doc.header
    insunits = header.get("$INSUNITS", 0)
    measurement = header.get("$MEASUREMENT", 0)
    extmin = header.get("$EXTMIN", (0, 0, 0))
    extmax = header.get("$EXTMAX", (0, 0, 0))
    width = extmax[0] - extmin[0]
    height = extmax[1] - extmin[1]

    insunit_names = {
        0: "unitless", 1: "inches", 2: "feet", 4: "millimeters",
        5: "centimeters", 6: "meters",
    }

    # ---- layers -----------------------------------------------------------
    layers = []
    for layer in doc.layers:
        layers.append({
            "name": layer.dxf.name,
            "color": layer.dxf.color,
            "linetype": layer.dxf.linetype,
            "is_off": layer.is_off(),
            "is_frozen": layer.is_frozen(),
        })

    # ---- block definitions -----------------------------------------------
    blocks = []
    for block in doc.blocks:
        if block.name.startswith("*"):
            continue
        ent_count = sum(1 for _ in block)
        blocks.append({"name": block.name, "entities": ent_count})

    # ---- entities in modelspace ------------------------------------------
    entity_counter: Counter = Counter()
    layer_usage: Counter = Counter()
    text_entries = []          # all readable labels in modelspace
    insert_layer_block: Counter = Counter()  # block reference usage by (block, layer)

    for e in msp:
        et = e.dxftype()
        entity_counter[et] += 1
        layer_usage[e.dxf.layer] += 1

        if et == "TEXT":
            try:
                ip = e.dxf.insert
                text_entries.append({
                    "type": "TEXT",
                    "layer": e.dxf.layer,
                    "text": e.dxf.text,
                    "x": float(ip[0]), "y": float(ip[1]),
                    "height": float(getattr(e.dxf, "height", 0.0)),
                })
            except Exception:
                pass
        elif et == "MTEXT":
            try:
                ip = e.dxf.insert
                # plain_text() removes formatting codes
                txt = e.plain_text() if hasattr(e, "plain_text") else e.text
                text_entries.append({
                    "type": "MTEXT",
                    "layer": e.dxf.layer,
                    "text": txt,
                    "x": float(ip[0]), "y": float(ip[1]),
                    "height": float(getattr(e.dxf, "char_height", 0.0)),
                })
            except Exception:
                pass
        elif et == "INSERT":
            block_name = e.dxf.name
            insert_layer_block[(block_name, e.dxf.layer)] += 1
            # attributes attached to the insert
            try:
                for attr in e.attribs:
                    text_entries.append({
                        "type": "ATTRIB",
                        "layer": e.dxf.layer,
                        "block": block_name,
                        "tag": attr.dxf.tag,
                        "text": attr.dxf.text,
                        "x": float(attr.dxf.insert[0]),
                        "y": float(attr.dxf.insert[1]),
                    })
            except Exception:
                pass

    # ---- write JSON outputs ----------------------------------------------
    LAYERS_JSON_PATH.write_text(json.dumps(
        {
            "layers": layers,
            "layer_usage_in_modelspace": layer_usage.most_common(),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    TEXTS_JSON_PATH.write_text(
        json.dumps(text_entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ---- text search ------------------------------------------------------
    facility_hits = defaultdict(list)
    for t in text_entries:
        body = (t.get("text") or "").strip()
        if not body:
            continue
        body_l = body.lower()
        for kw in FACILITY_KEYWORDS:
            # word-boundary-ish match for short keywords
            if len(kw) <= 3:
                if re.search(rf"(?<![a-zåäö]){re.escape(kw)}(?![a-zåäö])", body_l):
                    facility_hits[kw].append(t)
                    break
            elif kw in body_l:
                facility_hits[kw].append(t)
                break

    # ---- build report -----------------------------------------------------
    lines = []
    p = lines.append
    p("=" * 78)
    p(f"Skandinavium floorplan DXF analysis")
    p("=" * 78)
    p(f"File           : {DXF_PATH.name}")
    p(f"Size           : {DXF_PATH.stat().st_size/1024/1024:.2f} MB")
    p(f"AutoCAD ver.   : {header.get('$ACADVER', '?')}")
    p(f"Last saved by  : {header.get('$LASTSAVEDBY', '?')}")
    p(f"Units ($INSUNITS={insunits}) : {insunit_names.get(insunits, '?')}")
    p(f"Measurement    : {'metric' if measurement == 1 else 'imperial/unset'}")
    p(f"Extents min    : {extmin}")
    p(f"Extents max    : {extmax}")
    p(f"Drawing size   : {width:.1f} x {height:.1f} drawing-units")
    p(f"                 (~ {width/1000:.1f} x {height/1000:.1f} m if mm,"
      f"  {width:.1f} x {height:.1f} m if m)")
    p("")

    p("-" * 78)
    p(f"Layers ({len(layers)} defined)")
    p("-" * 78)
    p(f"{'Layer':45} {'Color':>5} {'#ent':>8} {'state':>10}")
    for layer in sorted(layers, key=lambda l: -layer_usage.get(l["name"], 0)):
        state = []
        if layer["is_off"]:
            state.append("off")
        if layer["is_frozen"]:
            state.append("frozen")
        p(f"{layer['name'][:45]:45} {layer['color']:>5} "
          f"{layer_usage.get(layer['name'], 0):>8} {','.join(state) or 'on':>10}")
    p("")

    p("-" * 78)
    p(f"Entity types in modelspace (total {sum(entity_counter.values())} entities)")
    p("-" * 78)
    for et, n in entity_counter.most_common():
        p(f"  {et:20} {n:>8}")
    p("")

    p("-" * 78)
    p(f"Block definitions ({len(blocks)})  - top 30 by entity count")
    p("-" * 78)
    for b in sorted(blocks, key=lambda b: -b["entities"])[:30]:
        p(f"  {b['name'][:50]:50} entities={b['entities']:>6}")
    p("")

    p("-" * 78)
    p("Most-used block references in modelspace (top 30)")
    p("-" * 78)
    block_usage = Counter()
    for (bname, _), n in insert_layer_block.items():
        block_usage[bname] += n
    for bname, n in block_usage.most_common(30):
        p(f"  {bname[:50]:50} inserts={n:>6}")
    p("")

    p("-" * 78)
    p(f"Text-like entities found: {len(text_entries)}")
    p(f"  TEXT  : {sum(1 for t in text_entries if t['type']=='TEXT')}")
    p(f"  MTEXT : {sum(1 for t in text_entries if t['type']=='MTEXT')}")
    p(f"  ATTRIB: {sum(1 for t in text_entries if t['type']=='ATTRIB')}")
    p("")

    p("-" * 78)
    p("Facility / room-related text matches")
    p("-" * 78)
    if not facility_hits:
        p("  (no obvious matches for restroom / WC / facility keywords)")
    else:
        for kw, hits in sorted(facility_hits.items(), key=lambda kv: -len(kv[1])):
            p(f"\n  keyword '{kw}'  ({len(hits)} hits)")
            for h in hits[:25]:
                p(f"    layer={h['layer']:30} ({h['x']:.1f}, {h['y']:.1f}) "
                  f"-> {h['text']!r}")
            if len(hits) > 25:
                p(f"    ... and {len(hits) - 25} more")
    p("")

    p("-" * 78)
    p("Sample of all text labels (first 60, sorted by layer)")
    p("-" * 78)
    for t in sorted(text_entries, key=lambda t: (t['layer'], t.get('text') or ''))[:60]:
        body = (t.get('text') or '').replace("\n", " | ")
        p(f"  [{t['layer'][:25]:25}] ({t['x']:9.1f}, {t['y']:9.1f}) {body[:80]}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote report -> {REPORT_PATH}")
    print(f"Wrote layers -> {LAYERS_JSON_PATH}")
    print(f"Wrote texts  -> {TEXTS_JSON_PATH}")


if __name__ == "__main__":
    main()
