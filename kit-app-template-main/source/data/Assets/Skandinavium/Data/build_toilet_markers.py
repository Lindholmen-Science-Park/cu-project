"""Build a UsdGeomPointInstancer of cube markers for each toilet POI.

Reads ``pois.json`` (produced by ``extract_pois.py``) and writes
``toilet_markers.usda`` next to it. The file is a stand-alone USD asset:

  * units are centimetres (matches the Skandinavium stage,
    ``metersPerUnit = 0.01``)
  * ``upAxis = "Y"``
  * a single PointInstancer with one cube prototype
  * per-instance colour primvar so toilet types are easy to tell apart
  * wrapped in a ``def Xform "POIMarkers"`` with identity translate /
    rotate / scale ops so it can be nudged onto the building without
    touching any of the instance data

Coordinate conversion DXF (mm, Z-up)  ->  USD (cm, Y-up):
    usd_x = dxf_x / 10
    usd_z = -dxf_y / 10
    usd_y = MARKER_Y_CM  (ground level, configurable)

NOTE: the DXF origin does not coincide with the USD stage origin. The
markers will appear at the correct relative layout but most likely
translated / rotated relative to the actual building. Edit the parent
Xform's ops to align.
"""

from __future__ import annotations

import json
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, Vt


HERE = Path(__file__).parent
POIS_JSON_PATH = HERE / "pois.json"
OUT_USDA_PATH = HERE / "toilet_markers.usda"

# Categories considered "toilets". Order matters: it controls the prototype /
# colour index the instance gets.
TOILET_CATEGORIES: list[tuple[str, tuple[float, float, float]]] = [
    # (category,                RGB colour for the cube)
    ("restroom_wheelchair",     (0.10, 0.55, 1.00)),  # blue   - RWC
    ("restroom_accessible",     (0.10, 0.85, 1.00)),  # cyan   - HWC
    ("restroom_women",          (1.00, 0.30, 0.65)),  # pink   - DAMTOALETT
    ("restroom_men",            (0.30, 0.55, 1.00)),  # blue   - HERRTOALETT
    ("restroom_generic",        (1.00, 0.85, 0.10)),  # yellow - WC / TOALETT
    ("restroom_anteroom",       (0.65, 0.65, 0.65)),  # grey   - FÖRRUM WC
]
CATEGORY_TO_INDEX = {cat: i for i, (cat, _) in enumerate(TOILET_CATEGORIES)}

# Marker geometry / placement -------------------------------------------------
CUBE_SIZE_CM = 200.0          # 2-metre cube, readable from a stadium bird-eye
MARKER_Y_CM = 100.0           # raise cubes 1 m above local ground so the
                              #   bottom face doesn't z-fight with the floor
INCLUDE_DUPLICATE_COPY = False  # set True to also place markers from the
                                # second annotated plan copy

# Coordinate conversion -------------------------------------------------------
MM_TO_CM = 0.1


def dxf_to_usd(x_mm: float, y_mm: float) -> Gf.Vec3f:
    """DXF (mm, Z-up) -> USD (cm, Y-up) in DXF-local space."""
    return Gf.Vec3f(
        float(x_mm) * MM_TO_CM,
        MARKER_Y_CM,
        -float(y_mm) * MM_TO_CM,
    )


def main() -> None:
    data = json.loads(POIS_JSON_PATH.read_text(encoding="utf-8"))
    pois = data["pois"]

    selected = [
        p for p in pois
        if p["category"] in CATEGORY_TO_INDEX
        and (INCLUDE_DUPLICATE_COPY or p["plan_copy"] == "main")
    ]
    print(f"Selected {len(selected)} toilet POIs from {len(pois)} total")

    # ---- create stage ----------------------------------------------------- #
    stage = Usd.Stage.CreateNew(str(OUT_USDA_PATH))
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    stage.SetDefaultPrim(stage.DefinePrim("/POIMarkers", "Xform"))

    root = UsdGeom.Xform.Get(stage, "/POIMarkers")

    # Identity ops on the root so callers have explicit knobs to align with
    # the Skandinavium stage. Edit these in usdview / your override layer.
    root.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))
    root.AddRotateYOp().Set(0.0)
    root.AddScaleOp().Set(Gf.Vec3f(1.0, 1.0, 1.0))

    # ---- prototype cube --------------------------------------------------- #
    UsdGeom.Scope.Define(stage, "/POIMarkers/Prototypes")
    cube = UsdGeom.Cube.Define(stage, "/POIMarkers/Prototypes/ToiletCube")
    cube.CreateSizeAttr(CUBE_SIZE_CM)
    cube.CreateDisplayColorAttr([Gf.Vec3f(1.0, 1.0, 1.0)])

    # ---- point instancer -------------------------------------------------- #
    instancer = UsdGeom.PointInstancer.Define(
        stage, "/POIMarkers/ToiletInstancer"
    )
    instancer.CreatePrototypesRel().SetTargets(
        [Sdf.Path("/POIMarkers/Prototypes/ToiletCube")]
    )

    positions: list[Gf.Vec3f] = []
    proto_indices: list[int] = []
    ids: list[int] = []
    colors: list[Gf.Vec3f] = []

    for i, p in enumerate(selected):
        positions.append(dxf_to_usd(p["dxf_x_mm"], p["dxf_y_mm"]))
        proto_indices.append(0)  # only one prototype; colour distinguishes
        ids.append(i)
        rgb = TOILET_CATEGORIES[CATEGORY_TO_INDEX[p["category"]]][1]
        colors.append(Gf.Vec3f(*rgb))

    instancer.CreatePositionsAttr(Vt.Vec3fArray(positions))
    instancer.CreateProtoIndicesAttr(Vt.IntArray(proto_indices))
    instancer.CreateIdsAttr(Vt.Int64Array(ids))

    # Per-instance colour via primvar (constant element-size, "vertex"
    # interpolation across instances).
    primvar_api = UsdGeom.PrimvarsAPI(instancer)
    color_pv = primvar_api.CreatePrimvar(
        "displayColor", Sdf.ValueTypeNames.Color3fArray,
        interpolation=UsdGeom.Tokens.vertex,
    )
    color_pv.Set(Vt.Vec3fArray(colors))

    # Side-car metadata: keep the labels around so future tooling can match
    # an instance index back to a POI without re-parsing pois.json.
    labels_attr = instancer.GetPrim().CreateAttribute(
        "userProperties:poi_labels", Sdf.ValueTypeNames.StringArray,
        custom=True,
    )
    labels_attr.Set(Vt.StringArray([p["label"] for p in selected]))

    categories_attr = instancer.GetPrim().CreateAttribute(
        "userProperties:poi_categories", Sdf.ValueTypeNames.StringArray,
        custom=True,
    )
    categories_attr.Set(Vt.StringArray([p["category"] for p in selected]))

    # ---- save ------------------------------------------------------------- #
    stage.GetRootLayer().documentation = (
        "Toilet POI markers for Skandinavium. Generated from "
        "Data/pois.json by build_toilet_markers.py. The PointInstancer "
        "lives in DXF-local space (cm, Y-up); align by editing the ops "
        "on /POIMarkers."
    )
    stage.GetRootLayer().Save()

    # ---- summary ---------------------------------------------------------- #
    print(f"\nWrote {OUT_USDA_PATH}")
    by_cat: dict[str, int] = {}
    for p in selected:
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    print("Markers by category:")
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:24} {n:>3}")
    print(f"  {'TOTAL':24} {len(selected):>3}")


if __name__ == "__main__":
    main()
