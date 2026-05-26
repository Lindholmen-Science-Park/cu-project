"""Generate `Instances/seated_people.usda` — a single
`UsdGeomPointInstancer` whose positions are sourced from the seat
instancer (`Assets/Seats/seats_instanced.usda`) at generation time.

Why:
  - We open the **already-authored** seat USD, read its PointInstancer
    arrays (so any composer-time overrides on seat positions flow
    through automatically), and emit one PointInstancer for the
    characters with positions = seat position + per-seat
    backrest offset + Z drop. No transform duplication, no drift if
    `seat_pivot_offset.py` is tweaked.

Output structure:

    /SeatedPeople                  (Xform, defaultPrim, crowd_density VS)
       /PeopleInstancer            (UsdGeomPointInstancer)
          /Prototypes
             /char_01 .. /char_09  (Xforms ref'ing the baked .usdc meshes
                                    directly — NOT the `instanceable=true`
                                    wrappers, which break GeomSubset
                                    material binding when used as a
                                    PointInstancer prototype.)

  `crowd_density` is authored on `/SeatedPeople` so the runtime backend
  (`younite.people_toggle_extension`) sees it on the composed
  `/World/Skandinavium/seated_people` prim. Variants flip the inner
  instancer's `invisibleIds` array (cheap, no shuffle).

What you have to regen for:
  - Adding/removing seats in the JSON.
  - Tweaking `BACKREST_OFFSET_MM` / `Z_OFFSET` here.
  - Editing `seat_pivot_offset.py` (then regen seats first, then this).
  - Manual composer-time edits to seat positions in `seats_instanced.usda`
    (those flow through positionally; rotations come from the JSON so
    seat-only manual rotations won't propagate without a JSON edit).

Usage:
    python generate_seated_pointinstancer.py
    python generate_seated_pointinstancer.py --variant half_capacity
"""

import argparse
import hashlib
import json
import math
import os
import random
import sys

from pxr import Gf, Sdf, Usd, UsdGeom, Vt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEAT_USD = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "Seats", "seats_instanced.usda"))
SEAT_JSON = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "Seats", "Data",
                 "extracted_seats_with_rows.json"))
OUTPUT_FILE = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "..", "Instances",
                 "seated_people.usda"))

SEATS_TOOLS_DIR = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "Seats", "Tools"))
if SEATS_TOOLS_DIR not in sys.path:
    sys.path.insert(0, SEATS_TOOLS_DIR)
from seat_pivot_offset import pivot_offset_dxy  # noqa: E402

# Reference the baked .usdc files directly (NOT the `characters/*.usda`
# wrappers). The wrappers set `instanceable = true`, which is exactly what
# we want for scene-graph instancing in the legacy per-seat-Xform layout
# but is the wrong thing for a PointInstancer prototype: Hydra's Fabric
# scene delegate cannot resolve GeomSubsets through an instanceable
# subtree under a PointInstancer prototype, the material bindings drop,
# and every character renders with the fallback flat-red colour.
# Bypassing the wrapper avoids the issue and saves a level of indirection.
PROTOTYPES = [
    {"name": "char_01", "baked": "char_01_bwom20008m4_ANI_baked.usdc"},
    {"name": "char_02", "baked": "char_02_cman20003m4_ANIv00001_baked.usdc"},
    {"name": "char_03", "baked": "char_03_cwom0309m4_ANIv00004_baked.usdc"},
    {"name": "char_04", "baked": "char_04_bman21092m4_ANIv00002_baked.usdc"},
    {"name": "char_05", "baked": "char_05_bman21096m4_ANIv00002_baked.usdc"},
    {"name": "char_06", "baked": "char_06_bman21108m4_ANIv00001_baked.usdc"},
    {"name": "char_07", "baked": "char_07_bwom0324m4_ANIv00001_baked.usdc"},
    {"name": "char_08", "baked": "char_08_bwom0325m4_ANI_baked.usdc"},
    {"name": "char_09", "baked": "char_09_bwom0328m4_ANIv00001_baked.usdc"},
]
BAKED_REL_DIR = "../Assets/People/PeopleSitting/baked"

EXCLUDED_TIERS = {"wheelchair", "companion"}
SEAT_INSTANCER_PATH = "/World/SeatInstancer"

PROTO_SCALE = 10.0  # cm props → mm seat space (matches legacy)

# Vertical offset (mm) so the baked sitting hips rest on the seat cushion.
Z_OFFSET = -450.0

# In-plane forward shift along seat's facing axis (mm). Same constant the
# legacy generator uses; see its docstring for sign convention.
BACKREST_OFFSET_MM = 160.0

# (variant, fraction_visible). Strict-subset order: smallest → largest.
DENSITY_VARIANTS = [
    ("none",   0.00),
    ("sparse", 0.60),
    ("medium", 0.75),
    ("dense",  0.90),
    ("full",   1.00),
]
DEFAULT_DENSITY_VARIANT = "none"
DENSITY_SHUFFLE_SEED = 4242


def rotation_deg_to_quath(deg):
    rad = math.radians(deg)
    return Gf.Quath(math.cos(rad / 2.0), 0.0, 0.0, math.sin(rad / 2.0))


def proto_index_for(seat_id, n_protos):
    """Stable per-seat prototype assignment via MD5 hash of the seat ID."""
    h = hashlib.md5(str(seat_id).encode("utf-8")).digest()
    return h[0] % n_protos


def read_seat_arrays(seat_variant):
    """Open the seat USD, switch to `seat_variant`, return (positions, ids)."""
    print(f"Opening seat USD: {SEAT_USD}")
    stage = Usd.Stage.Open(SEAT_USD)
    if not stage:
        raise RuntimeError(f"Could not open {SEAT_USD}")

    instancer_prim = stage.GetPrimAtPath(SEAT_INSTANCER_PATH)
    if not instancer_prim or not instancer_prim.IsValid():
        raise RuntimeError(
            f"Seat PointInstancer not found at {SEAT_INSTANCER_PATH}")

    vsets = instancer_prim.GetVariantSets()
    if "seating" in vsets.GetNames():
        seating_vset = vsets.GetVariantSet("seating")
        available = seating_vset.GetVariantNames()
        if seat_variant not in available:
            raise RuntimeError(
                f"Seat variant '{seat_variant}' not in {available}")
        seating_vset.SetVariantSelection(seat_variant)
        print(f"  seating variant = '{seat_variant}'")

    instancer = UsdGeom.PointInstancer(instancer_prim)
    positions = instancer.GetPositionsAttr().Get() or []
    pv_api = UsdGeom.PrimvarsAPI(instancer_prim)
    seat_id_pv = pv_api.GetPrimvar("seatId")
    if not seat_id_pv:
        raise RuntimeError("Seat instancer missing 'seatId' primvar")
    seat_ids = list(seat_id_pv.Get() or [])

    if len(positions) != len(seat_ids):
        raise RuntimeError(
            f"Seat array length mismatch: {len(positions)} positions "
            f"vs {len(seat_ids)} ids")
    print(f"  {len(positions)} seats in instancer")
    return positions, seat_ids


def load_seat_meta():
    with open(SEAT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {s["id"]: s for s in data}


def build_character_arrays(positions, seat_ids, seat_meta):
    char_pos, char_ori, char_scl, char_idx, char_ids = [], [], [], [], []
    char_seat_ids = []
    skipped_excluded = 0
    skipped_unknown = 0
    next_id = 0
    for i, sid in enumerate(seat_ids):
        meta = seat_meta.get(sid)
        if meta is None:
            skipped_unknown += 1
            continue
        if meta.get("tier") in EXCLUDED_TIERS:
            skipped_excluded += 1
            continue
        rot_deg = float(meta.get("rotation", 0.0))
        bdx, bdy = pivot_offset_dxy(rot_deg, BACKREST_OFFSET_MM)
        sp = positions[i]
        char_pos.append(Gf.Vec3f(sp[0] + bdx, sp[1] + bdy, sp[2] + Z_OFFSET))
        char_ori.append(rotation_deg_to_quath(rot_deg))
        char_scl.append(Gf.Vec3f(PROTO_SCALE, PROTO_SCALE, PROTO_SCALE))
        char_idx.append(proto_index_for(sid, len(PROTOTYPES)))
        char_ids.append(next_id)
        char_seat_ids.append(str(sid))
        next_id += 1
    return {
        "positions": char_pos,
        "orientations": char_ori,
        "scales": char_scl,
        "proto_indices": char_idx,
        "ids": char_ids,
        "seat_ids": char_seat_ids,
        "skipped_excluded": skipped_excluded,
        "skipped_unknown": skipped_unknown,
    }


def compute_density_invisible_ids(char_ids):
    """For each density variant, return the list of instance IDs to hide."""
    n = len(char_ids)
    order = list(range(n))
    random.Random(DENSITY_SHUFFLE_SEED).shuffle(order)
    out = {}
    for variant_name, fraction in DENSITY_VARIANTS:
        keep = int(fraction * n)
        visible_ranks = set(order[:keep])
        out[variant_name] = [char_ids[i] for i in range(n)
                             if i not in visible_ranks]
    return out


def write_usd(arrays, density_hidden):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    stage = Usd.Stage.CreateNew(OUTPUT_FILE)
    stage.SetMetadata("upAxis", "Z")
    UsdGeom.SetStageMetersPerUnit(stage, 0.001)

    root = UsdGeom.Xform.Define(stage, "/SeatedPeople")
    stage.SetDefaultPrim(root.GetPrim())

    pi_path = "/SeatedPeople/PeopleInstancer"
    pi = UsdGeom.PointInstancer.Define(stage, pi_path)

    proto_scope_path = f"{pi_path}/Prototypes"
    UsdGeom.Scope.Define(stage, proto_scope_path)
    proto_targets = []
    for proto in PROTOTYPES:
        ppath = f"{proto_scope_path}/{proto['name']}"
        proto_xf = UsdGeom.Xform.Define(stage, ppath)
        proto_xf.GetPrim().GetReferences().AddReference(
            f"{BAKED_REL_DIR}/{proto['baked']}")
        proto_targets.append(Sdf.Path(ppath))
    pi.GetPrototypesRel().SetTargets(proto_targets)

    pi.GetPositionsAttr().Set(Vt.Vec3fArray(arrays["positions"]))
    pi.GetOrientationsAttr().Set(Vt.QuathArray(arrays["orientations"]))
    pi.GetScalesAttr().Set(Vt.Vec3fArray(arrays["scales"]))
    pi.GetProtoIndicesAttr().Set(Vt.IntArray(arrays["proto_indices"]))
    pi.GetIdsAttr().Set(Vt.Int64Array(arrays["ids"]))

    # Per-instance seatId primvar (mirror of the seat instancer's). Lets the
    # navmesh_route_extension's seated_crowd_highlight map a seat ID to the
    # corresponding crowd instance id so it can hide that one character while
    # the seat is highlighted as the navigation target.
    pv_api = UsdGeom.PrimvarsAPI(pi.GetPrim())
    seat_id_pv = pv_api.CreatePrimvar(
        "seatId", Sdf.ValueTypeNames.StringArray,
        interpolation=UsdGeom.Tokens.varying)
    seat_id_pv.Set(Vt.StringArray(arrays["seat_ids"]))

    # crowd_density VariantSet on /SeatedPeople — each variant flips the
    # inner instancer's invisibleIds. Lives on the root so the runtime
    # extension can flip it on /World/Skandinavium/seated_people.
    vset = root.GetPrim().GetVariantSets().AddVariantSet("crowd_density")
    for variant_name, _ in DENSITY_VARIANTS:
        vset.AddVariant(variant_name)
        vset.SetVariantSelection(variant_name)
        with vset.GetVariantEditContext():
            UsdGeom.PointInstancer(stage.GetPrimAtPath(pi_path)) \
                .GetInvisibleIdsAttr() \
                .Set(Vt.Int64Array(density_hidden[variant_name]))
    vset.SetVariantSelection(DEFAULT_DENSITY_VARIANT)

    stage.GetRootLayer().Save()


def main():
    parser = argparse.ArgumentParser(
        description="Generate seated_people.usda from seats_instanced.usda")
    parser.add_argument("--variant", default="all_seats",
                        help="seating variant to mirror "
                             "(all_seats / half_capacity / one_third_capacity / "
                             "event_playstation_c). Default: all_seats")
    args = parser.parse_args()

    positions, seat_ids = read_seat_arrays(args.variant)
    seat_meta = load_seat_meta()
    arrays = build_character_arrays(positions, seat_ids, seat_meta)

    n = len(arrays["positions"])
    print(f"  Skipped (excluded tier): {arrays['skipped_excluded']}")
    print(f"  Skipped (no JSON match): {arrays['skipped_unknown']}")
    print(f"  Characters to place: {n}")

    density_hidden = compute_density_invisible_ids(arrays["ids"])
    write_usd(arrays, density_hidden)

    print(f"\nGenerated: {OUTPUT_FILE}")
    print(f"  File size: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")
    print(f"  Default crowd_density: {DEFAULT_DENSITY_VARIANT}")
    print("\nCrowd density variants:")
    for name, _ in DENSITY_VARIANTS:
        hidden = len(density_hidden[name])
        visible = n - hidden
        pct = (visible * 100) // max(1, n)
        print(f"  {name:8s}  visible={visible:5d}  hidden={hidden:5d}  ({pct}%)")


if __name__ == "__main__":
    main()
