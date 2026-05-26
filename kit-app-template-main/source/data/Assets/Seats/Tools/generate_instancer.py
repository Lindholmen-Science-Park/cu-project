"""Generate a PointInstancer USD from extracted_seats_with_rows.json.

Source asset: ``Scan-Arenaseats.usdc`` — provides four prototype meshes
sharing identical pivots:

  * ``SeatScandOrange_Up_001``   — orange (upper tier), folded UP   (empty)
  * ``SeatScandOrange_Down_001`` — orange (upper tier), folded DOWN (occupied / nav target)
  * ``SeatScandWhite_Up_001``    — white  (lower tier), folded UP   (empty)
  * ``SeatScandWhite_Down_001``  — white  (lower tier), folded DOWN (occupied / nav target)

Prototype index layout written to ``seats_instanced.usda``:

  * 0 = ChairOrangeUp     (default for upper-tier seats)
  * 1 = ChairWhiteUp      (default for lower-tier seats)
  * 2 = ChairOrangeDown   (runtime: occupied upper / nav target)
  * 3 = ChairWhiteDown    (runtime: occupied lower / nav target)
  * 4 = ChairHighlight    (runtime: green-glow nav target — Down geometry)

Default ``protoIndices`` only ever contain Up indices (0 / 1). Down + Highlight
are session-layer overlays driven at runtime by ``seat_fold_state`` and
``seat_highlight`` (both routing through ``seat_proto_override``).

Usage:
    python generate_instancer.py            # outputs .usda (text)
    python generate_instancer.py --usdc     # outputs .usdc (binary, smaller/faster)

Requires: pxr (OpenUSD)
"""

from pxr import Usd, UsdGeom, UsdShade, Gf, Vt, Sdf
import argparse
import json
import math
import os

from seat_pivot_offset import visual_seat_xy_mm

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEATS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SEATS_DIR, "Data")
SOURCE_USD = os.path.join(SEATS_DIR, "Scan-Arenaseats.usdc")
SEATS_JSON = os.path.join(DATA_DIR, "extracted_seats_with_rows.json")
CONFIG_DIR = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "..", "..", "extensions",
    "younite.navmesh_route_extension", "config"))

PROTO_SCALE = 10.0
ROTATION_OFFSET = 180.0

LOWER_TIERS = {"lower", "lower2", "extra_lower", "parkett"}

# Source asset paths under /World/ArenaSeatV2/<Xform>/<Mesh>
ARENA_SEAT_ROOT = "/World/ArenaSeatV2"
SOURCE_PROTOTYPES = [
    # (proto_name, source_xform, default_material_for_seat)
    ("ChairOrangeUp",   "SeatScandOrange_Up_001",   "VIS_Orangeplastic"),
    ("ChairWhiteUp",    "SeatScandWhite_Up_001",    "VIS_Whiteplastic"),
    ("ChairOrangeDown", "SeatScandOrange_Down_001", "VIS_Orangeplastic"),
    ("ChairWhiteDown",  "SeatScandWhite_Down_001",  "VIS_Whiteplastic"),
]
HIGHLIGHT_SOURCE_XFORM = "SeatScandOrange_Down_001"  # Down geometry, recoloured

# Prototype indices (must stay in sync with seat_proto_override / seat_highlight)
PROTO_ORANGE_UP = 0
PROTO_WHITE_UP = 1
PROTO_ORANGE_DOWN = 2
PROTO_WHITE_DOWN = 3
PROTO_HIGHLIGHT = 4

# Material colours read from Scan-Arenaseats.usdc UsdPreviewSurface inputs.
# Authored as OmniPBR MDL so they composite identically to the rest of the
# scene (and side-step the "Unable to find SdrShaderNode" failure mode that
# absolute-path MDL refs cause — see seated-crowd.mdc).
SOURCE_MATERIAL_COLORS = {
    "VIS_Orangeplastic": Gf.Vec3f(0.44956774, 0.20138972, 0.111420244),
    "VIS_Whiteplastic":  Gf.Vec3f(0.2651297,  0.26512703, 0.26512703),
    "VIS_Svartgeneric":  Gf.Vec3f(0.011527244, 0.0115273595, 0.011527244),
}
SOURCE_MATERIAL_ROUGHNESS = {
    "VIS_Orangeplastic": 0.28,
    "VIS_Whiteplastic":  0.30,
    "VIS_Svartgeneric":  0.29,
}


# ── Prototype geometry extraction ─────────────────────────────────────────

def extract_arena_prototype(stage, source_xform_name):
    """Read a single prototype mesh from ``/World/ArenaSeatV2/<xform>``.

    Returns a dict of geometry + per-subset material binding info ready
    for ``create_mesh_prim``. The parent Xform's transform is
    intentionally **not** applied:

    * The mesh is already authored ``+Z = up`` (bbox: X=45 cm wide,
      Z=90 cm tall, Y=20-46 cm depth) — exactly the orientation our
      Z-up output stage wants.
    * The source file's ``(-90°, 0, 0)`` parent rotation existed only
      to display this Z-up mesh inside the source's *Y-up* stage. In
      our Z-up output, applying it would lay the chairs flat on their
      backs.
    * The small parent translate ``(0, -2.748, 3.135) cm`` is also
      dropped so the chair pivot matches the previous pipeline
      (preserves seat positions, ``BACKREST_OFFSET_MM``, row Z-heights).
    """
    xform_path = f"{ARENA_SEAT_ROOT}/{source_xform_name}"
    xform_prim = stage.GetPrimAtPath(xform_path)
    if not xform_prim or not xform_prim.IsValid():
        raise RuntimeError(f"Prototype source not found: {xform_path}")

    # Find the Mesh child (same name as the parent Xform in this asset).
    mesh_prim = next(
        (c for c in xform_prim.GetChildren() if c.GetTypeName() == "Mesh"),
        None,
    )
    if mesh_prim is None:
        raise RuntimeError(f"No Mesh under {xform_path}")

    mesh = UsdGeom.Mesh(mesh_prim)
    data = {
        "points": mesh.GetPointsAttr().Get(),
        "faceVertexCounts": mesh.GetFaceVertexCountsAttr().Get(),
        "faceVertexIndices": mesh.GetFaceVertexIndicesAttr().Get(),
        "normals": mesh.GetNormalsAttr().Get(),
        "normals_interpolation": mesh.GetNormalsInterpolation(),
    }

    pv_api = UsdGeom.PrimvarsAPI(mesh_prim)
    st_pv = pv_api.GetPrimvar("st")
    if st_pv and st_pv.HasValue():
        data["uvs"] = st_pv.Get()
        data["uv_indices"] = st_pv.GetIndices()
        data["uv_interpolation"] = st_pv.GetInterpolation()

    subsets = []
    for child in mesh_prim.GetChildren():
        if child.GetTypeName() != "GeomSubset":
            continue
        subset = UsdGeom.Subset(child)
        mat_api = UsdShade.MaterialBindingAPI(child)
        mat_path = str(mat_api.GetDirectBinding().GetMaterialPath() or "")
        # mat_path looks like "/World/ArenaSeatV2/Looks/VIS_Orangeplastic" —
        # strip to just the material name.
        mat_name = mat_path.rsplit("/", 1)[-1] if mat_path else ""
        subsets.append({
            "name": child.GetName(),
            "indices": subset.GetIndicesAttr().Get(),
            "familyName": subset.GetFamilyNameAttr().Get(),
            "elementType": subset.GetElementTypeAttr().Get(),
            "material_name": mat_name,
        })
    data["subsets"] = subsets
    return data


# ── Material authoring (OmniPBR MDL inline) ──────────────────────────────

def _create_omnipbr_material(stage, mat_path, diffuse_color, roughness,
                             emissive_color=None, emissive_intensity=0.0):
    mat = UsdShade.Material.Define(stage, mat_path)
    sh_path = f"{mat_path}/Shader"
    sh = UsdShade.Shader.Define(stage, sh_path)
    p = sh.GetPrim()
    p.CreateAttribute("info:implementationSource",
                      Sdf.ValueTypeNames.Token, custom=False).Set("sourceAsset")
    p.CreateAttribute("info:mdl:sourceAsset",
                      Sdf.ValueTypeNames.Asset, custom=False
                      ).Set(Sdf.AssetPath("OmniPBR.mdl"))
    p.CreateAttribute("info:mdl:sourceAsset:subIdentifier",
                      Sdf.ValueTypeNames.Token, custom=False).Set("OmniPBR")
    sh.CreateInput("diffuse_color_constant",
                   Sdf.ValueTypeNames.Color3f).Set(diffuse_color)
    sh.CreateInput("reflection_roughness_constant",
                   Sdf.ValueTypeNames.Float).Set(roughness)
    sh.CreateInput("metallic_constant",
                   Sdf.ValueTypeNames.Float).Set(0.0)
    if emissive_color is not None and emissive_intensity > 0.0:
        sh.CreateInput("enable_emission",
                       Sdf.ValueTypeNames.Bool).Set(True)
        sh.CreateInput("emissive_color",
                       Sdf.ValueTypeNames.Color3f).Set(emissive_color)
        sh.CreateInput("emissive_intensity",
                       Sdf.ValueTypeNames.Float).Set(emissive_intensity)
    sh.CreateOutput("out", Sdf.ValueTypeNames.Token)
    conn = sh.ConnectableAPI()
    mat.CreateSurfaceOutput(renderContext="mdl").ConnectToSource(conn, "out")
    mat.CreateDisplacementOutput(renderContext="mdl").ConnectToSource(conn, "out")
    mat.CreateVolumeOutput(renderContext="mdl").ConnectToSource(conn, "out")
    return mat_path


def write_materials(stage, root="/World"):
    """Author all materials inline (no extraction from source).

    Returns ``{material_name: prim_path}`` mapping used to bind GeomSubsets.
    """
    stage.DefinePrim(f"{root}/Looks", "Scope")
    mat_path_map = {}
    for name, color in SOURCE_MATERIAL_COLORS.items():
        path = f"{root}/Looks/{name}"
        roughness = SOURCE_MATERIAL_ROUGHNESS.get(name, 0.5)
        _create_omnipbr_material(stage, path, color, roughness)
        mat_path_map[name] = path
    return mat_path_map


def create_highlight_material(stage, mat_path_map, root="/World"):
    """Bright green emissive material used by the seat-nav target prototype."""
    hl_path = f"{root}/Looks/HighlightMaterial"
    _create_omnipbr_material(
        stage, hl_path,
        diffuse_color=Gf.Vec3f(0.2, 0.9, 0.3),
        roughness=0.4,
        emissive_color=Gf.Vec3f(0.2, 1.0, 0.3),
        emissive_intensity=5000.0,
    )
    mat_path_map["HighlightMaterial"] = hl_path


def create_mesh_prim(stage, mesh_path, proto_data, mat_path_map,
                     subset_material_override=None):
    """Define a mesh + GeomSubsets + material bindings.

    ``subset_material_override`` is an optional ``{subset_name: mat_name}``
    map used by the highlight prototype to redirect every subset to the
    green material regardless of its source binding.
    """
    mesh = UsdGeom.Mesh.Define(stage, mesh_path)
    mesh.GetPointsAttr().Set(proto_data["points"])
    mesh.GetFaceVertexCountsAttr().Set(proto_data["faceVertexCounts"])
    mesh.GetFaceVertexIndicesAttr().Set(proto_data["faceVertexIndices"])
    if proto_data.get("normals"):
        mesh.GetNormalsAttr().Set(proto_data["normals"])
        mesh.SetNormalsInterpolation(proto_data["normals_interpolation"])
    if "uvs" in proto_data:
        pv = UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray,
            proto_data["uv_interpolation"])
        pv.Set(proto_data["uvs"])
        if proto_data["uv_indices"]:
            pv.SetIndices(proto_data["uv_indices"])

    for sd in proto_data["subsets"]:
        sp = f"{mesh_path}/{sd['name']}"
        subset = UsdGeom.Subset.Define(stage, sp)
        subset.GetIndicesAttr().Set(sd["indices"])
        if sd["elementType"]:
            subset.GetElementTypeAttr().Set(sd["elementType"])
        if sd["familyName"]:
            subset.GetFamilyNameAttr().Set(sd["familyName"])
        mat_name = sd.get("material_name") or ""
        if subset_material_override:
            mat_name = subset_material_override.get(sd["name"], mat_name)
        if mat_name and mat_name in mat_path_map:
            UsdShade.MaterialBindingAPI.Apply(
                stage.GetPrimAtPath(sp)
            ).Bind(UsdShade.Material(
                stage.GetPrimAtPath(mat_path_map[mat_name])))


def compute_quaternion_z(angle_deg):
    rad = math.radians(angle_deg)
    return Gf.Quath(math.cos(rad / 2.0), 0.0, 0.0, math.sin(rad / 2.0))


# ── Availability generation ──────────────────────────────────────────────

def generate_availability(all_seats, skip):
    """Pick every Nth seat within each (section, row), return set of IDs."""
    grouped = {}
    for s in all_seats:
        key = (s.get("section", ""), str(s.get("row", "")))
        grouped.setdefault(key, []).append(s)

    available = []
    for key in sorted(grouped):
        row_seats = grouped[key]
        try:
            row_seats.sort(key=lambda s: int(s["seat_number"]))
        except (ValueError, KeyError):
            row_seats.sort(key=lambda s: str(s.get("seat_number", "")))
        for i, seat in enumerate(row_seats):
            if i % skip == 0:
                available.append(seat["id"])
    return available


def write_availability(ids, event_name, filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w') as f:
        json.dump({"event": event_name, "available_seats": sorted(ids)},
                  f, indent=2)
    print(f"  Wrote {filename} ({len(ids)} seats)")
    return path


# ── Instance arrays ──────────────────────────────────────────────────────

def build_instance_arrays(seats):
    """Build PointInstancer arrays from seat dicts (non-wheelchair only).

    All seats default to the *Up* (folded) prototype — Down + Highlight
    are runtime session-layer overlays.
    """
    pos, ori, scl, idx, ids = [], [], [], [], []
    for s in seats:
        vx, vy = visual_seat_xy_mm(s)
        pos.append(Gf.Vec3f(vx, vy, s["z"]))
        ori.append(compute_quaternion_z(s.get("rotation", 0) + ROTATION_OFFSET))
        scl.append(Gf.Vec3f(PROTO_SCALE, PROTO_SCALE, PROTO_SCALE))
        proto = (PROTO_WHITE_UP if s.get("tier", "upper") in LOWER_TIERS
                 else PROTO_ORANGE_UP)
        idx.append(proto)
        ids.append(s["id"])
    return pos, ori, scl, idx, ids


def set_instancer_arrays(instancer, pos, ori, scl, idx, ids):
    instancer.GetPositionsAttr().Set(Vt.Vec3fArray(pos))
    instancer.GetOrientationsAttr().Set(Vt.QuathArray(ori))
    instancer.GetScalesAttr().Set(Vt.Vec3fArray(scl))
    instancer.GetProtoIndicesAttr().Set(Vt.IntArray(idx))

    pv = UsdGeom.PrimvarsAPI(instancer.GetPrim()).CreatePrimvar(
        "seatId", Sdf.ValueTypeNames.StringArray, UsdGeom.Tokens.varying)
    pv.Set(ids)


def filter_by_availability(seats, avail_ids):
    avail_set = set(avail_ids)
    return [s for s in seats if s["id"] in avail_set]


# ── Lookup generation ────────────────────────────────────────────────────

def write_lookup(all_seats):
    """Write seats_lookup.json mapping seat ID → [x, y, z]."""
    lookup = {}
    for s in all_seats:
        lookup[s["id"]] = [round(s["x"], 1), round(s["y"], 1), round(s["z"], 1)]

    os.makedirs(CONFIG_DIR, exist_ok=True)
    out = os.path.join(CONFIG_DIR, "seats_lookup.json")
    with open(out, 'w') as f:
        json.dump(lookup, f, separators=(',', ':'))
    print(f"  Wrote seats_lookup.json ({len(lookup)} seats, "
          f"{os.path.getsize(out) / 1024:.0f} KB)")


# ── Variant config ───────────────────────────────────────────────────────

def write_variant_config(variant_specs):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    config = {}
    for name, avail_file in variant_specs:
        if avail_file:
            config_name = f"availability_{name}.json"
            src = os.path.normpath(
                avail_file if os.path.isabs(avail_file)
                else os.path.join(DATA_DIR, avail_file))
            dst = os.path.join(CONFIG_DIR, config_name)
            with open(src) as f:
                data = json.load(f)
            with open(dst, 'w') as f:
                json.dump(data, f, separators=(',', ':'))
            config[name] = config_name
        else:
            config[name] = None

    out = os.path.join(CONFIG_DIR, "seating_variants.json")
    with open(out, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"  Wrote seating_variants.json -> {out}")


# ── Prototype writing ────────────────────────────────────────────────────

def define_prototype(stage, proto_name, proto_data, mat_path_map,
                     subset_material_override=None):
    base = f"/World/SeatInstancer/Prototypes/{proto_name}"
    UsdGeom.Xform.Define(stage, base)
    create_mesh_prim(stage, f"{base}/ChairMesh", proto_data, mat_path_map,
                     subset_material_override=subset_material_override)
    return Sdf.Path(base)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate PointInstancer USD from extracted seat data")
    parser.add_argument("--usdc", action="store_true",
                        help="Output binary .usdc instead of text .usda")
    args = parser.parse_args()

    ext = ".usdc" if args.usdc else ".usda"
    output_path = os.path.join(SEATS_DIR, f"seats_instanced{ext}")

    print(f"Loading source USD for prototypes: {os.path.basename(SOURCE_USD)}")
    source_stage = Usd.Stage.Open(SOURCE_USD)
    proto_geometry = {}
    for proto_name, source_xform, _ in SOURCE_PROTOTYPES:
        proto_geometry[proto_name] = extract_arena_prototype(
            source_stage, source_xform)
        pd = proto_geometry[proto_name]
        print(f"  {proto_name:<18}  ({source_xform}): "
              f"{len(pd['points'])} pts, "
              f"{len(pd['faceVertexCounts'])} faces, "
              f"{len(pd['subsets'])} subsets")
    highlight_geometry = extract_arena_prototype(
        source_stage, HIGHLIGHT_SOURCE_XFORM)

    print(f"\nLoading seats from {os.path.basename(SEATS_JSON)}...")
    with open(SEATS_JSON, encoding="utf-8") as f:
        all_seats = json.load(f)
    print(f"  {len(all_seats)} total seats")

    chair_seats = [s for s in all_seats
                   if s.get("tier") not in ("wheelchair", "companion")]
    wc_seats = [s for s in all_seats if s.get("tier") == "wheelchair"]
    comp_seats = [s for s in all_seats if s.get("tier") == "companion"]
    print(f"  {len(chair_seats)} chairs + {len(wc_seats)} wheelchair spots"
          f" + {len(comp_seats)} companion seats")

    # ── Generate availability files ──
    wc_ids = [s["id"] for s in wc_seats]
    print("\nGenerating availability files...")
    all_ids = [s["id"] for s in chair_seats] + wc_ids
    all_file = write_availability(
        all_ids, "all_seats", "availability_all_seats.json")

    half_ids = generate_availability(chair_seats, skip=2) + wc_ids
    half_file = write_availability(
        half_ids, "half_capacity", "availability_half.json")

    third_ids = generate_availability(chair_seats, skip=3) + wc_ids
    third_file = write_availability(
        third_ids, "one_third_capacity", "availability_third.json")

    variant_specs = [
        ("all_seats", all_file),
        ("half_capacity", half_file),
        ("one_third_capacity", third_file),
    ]

    # ── Create output stage ──
    print(f"\nCreating {os.path.basename(output_path)}...")
    stage = Usd.Stage.CreateNew(output_path)
    stage.SetMetadata("upAxis", "Z")
    UsdGeom.SetStageMetersPerUnit(stage, 0.001)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(100)
    stage.SetTimeCodesPerSecond(60)

    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())

    # ── Materials ──
    mat_path_map = write_materials(stage)
    create_highlight_material(stage, mat_path_map)

    # ── Prototypes (5 total: 4 chair states + 1 highlight) ──
    instancer = UsdGeom.PointInstancer.Define(stage, "/World/SeatInstancer")
    proto_scope = stage.DefinePrim("/World/SeatInstancer/Prototypes", "Scope")
    proto_scope.SetSpecifier(Sdf.SpecifierDef)

    proto_targets = []
    for proto_name, _, _ in SOURCE_PROTOTYPES:
        proto_targets.append(define_prototype(
            stage, proto_name, proto_geometry[proto_name], mat_path_map))

    # Highlight prototype: Down geometry, every subset rebound to the green
    # material so the orange/white plastic + black frame all glow.
    highlight_override = {sd["name"]: "HighlightMaterial"
                          for sd in highlight_geometry["subsets"]}
    proto_targets.append(define_prototype(
        stage, "ChairHighlight", highlight_geometry, mat_path_map,
        subset_material_override=highlight_override))

    instancer.GetPrototypesRel().SetTargets(proto_targets)

    # ── VariantSet "seating" ──
    instancer_prim = instancer.GetPrim()
    vset = instancer_prim.GetVariantSets().AddVariantSet("seating")

    comp_pos, comp_ori, comp_scl, comp_idx, comp_ids = \
        build_instance_arrays(comp_seats) if comp_seats else ([], [], [], [], [])

    for vname, avail_file in variant_specs:
        if avail_file:
            with open(avail_file) as f:
                avail_data = json.load(f)
            seats = filter_by_availability(chair_seats, avail_data["available_seats"])
        else:
            seats = chair_seats

        pos, ori, scl, idx, ids = build_instance_arrays(seats)
        pos += comp_pos
        ori += comp_ori
        scl += comp_scl
        idx += comp_idx
        ids += comp_ids
        n_upper = sum(1 for i in idx if i == PROTO_ORANGE_UP)
        n_lower = sum(1 for i in idx if i == PROTO_WHITE_UP)
        print(f"  Variant '{vname}': {len(seats)} chairs + {len(comp_seats)} "
              f"companion (orange_up={n_upper}, white_up={n_lower})")

        vset.AddVariant(vname)
        vset.SetVariantSelection(vname)
        with vset.GetVariantEditContext():
            set_instancer_arrays(instancer, pos, ori, scl, idx, ids)

    # ── Event variant (from separate event extraction) ──
    EVENT_SEATS_JSON = os.path.join(DATA_DIR, "extracted_event_seats.json")
    if os.path.isfile(EVENT_SEATS_JSON):
        print(f"\nLoading event seats from {os.path.basename(EVENT_SEATS_JSON)}...")
        with open(EVENT_SEATS_JSON, encoding="utf-8") as f:
            event_all = json.load(f)
        event_chairs = [s for s in event_all
                        if s.get("tier") not in ("wheelchair", "companion")]
        event_wc = [s for s in event_all if s.get("tier") == "wheelchair"]
        event_comp = [s for s in event_all if s.get("tier") == "companion"]
        print(f"  {len(event_chairs)} chairs + {len(event_wc)} wheelchair spots"
              f" + {len(event_comp)} companion seats")

        ev_comp_pos, ev_comp_ori, ev_comp_scl, ev_comp_idx, ev_comp_ids = \
            build_instance_arrays(event_comp) if event_comp else ([], [], [], [], [])

        vname = "event_playstation_c"
        pos, ori, scl, idx, ids = build_instance_arrays(event_chairs)
        pos += ev_comp_pos
        ori += ev_comp_ori
        scl += ev_comp_scl
        idx += ev_comp_idx
        ids += ev_comp_ids
        n_upper = sum(1 for i in idx if i == PROTO_ORANGE_UP)
        n_lower = sum(1 for i in idx if i == PROTO_WHITE_UP)
        print(f"  Variant '{vname}': {len(event_chairs)} chairs + "
              f"{len(event_comp)} companion "
              f"(orange_up={n_upper}, white_up={n_lower})")

        vset.AddVariant(vname)
        vset.SetVariantSelection(vname)
        with vset.GetVariantEditContext():
            set_instancer_arrays(instancer, pos, ori, scl, idx, ids)

        event_wc_ids = [s["id"] for s in event_wc]
        event_avail_ids = [s["id"] for s in event_chairs] + event_wc_ids
        event_avail_file = write_availability(
            event_avail_ids, vname, "availability_event_playstation_c.json")
        variant_specs.append((vname, event_avail_file))

    vset.SetVariantSelection("all_seats")

    # ── Wheelchair spots (position-only Xforms) ──
    if wc_seats:
        UsdGeom.Xform.Define(stage, "/World/WheelchairSpots")
        for s in wc_seats:
            safe_name = s["id"].replace("-", "_")
            xf = UsdGeom.Xform.Define(
                stage, f"/World/WheelchairSpots/{safe_name}")
            xf.AddTranslateOp().Set(Gf.Vec3d(s["x"], s["y"], s["z"]))
            xf.AddRotateZOp().Set(s.get("rotation", 0.0))
            xf_prim = xf.GetPrim()
            xf_prim.CreateAttribute(
                "seatId", Sdf.ValueTypeNames.String, custom=True
            ).Set(s["id"])
        print(f"  {len(wc_seats)} wheelchair Xforms under /World/WheelchairSpots")

    stage.GetRootLayer().Save()

    # ── Config files ──
    print("\nWriting config files...")
    write_variant_config(variant_specs)
    print("  NOTE: Run create_lookup.py separately to generate world-space seats_lookup.json")

    file_size = os.path.getsize(output_path)
    print(f"\nDone!  {output_path}")
    print(f"  File size: {file_size / (1024*1024):.1f} MB")
    print(f"  Prototypes: 5 (OrangeUp + WhiteUp + OrangeDown + WhiteDown + Highlight)")
    print(f"  Variants: {[v[0] for v in variant_specs]}")
    print(f"  Wheelchair spots: {len(wc_seats)}")
    print(f"  Companion seats: {len(comp_seats)} (visual only, all variants)")


if __name__ == "__main__":
    main()
