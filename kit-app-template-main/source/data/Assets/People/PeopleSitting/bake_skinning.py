"""Bake the 9 sitting-character variants to a **static** (single-frame) mesh.

We discovered that:
  - UsdSkel skinning does not survive scene-graph instancing in Omniverse RTX
    (characters T-pose).
  - Bringing in 11.5k unique skinned characters blows up VRAM.
  - A baked, time-sampled mesh works but the timeline doesn't loop reliably
    and per-frame point evaluation contributes to startup lag.

So we bake **just frame 0** of each animation (the natural sitting pose) and
write the result as static `points` / `normals` / `extent` (no time samples).
Hydra treats these as plain static meshes — they instance perfectly across
~11.5k seats, with zero per-frame skinning or point-buffer churn.

For each variant we:
  1. Compose prop + animation into an in-memory stage.
  2. Bind `skel:animationSource` on the SkelRoot.
  3. Run `pxr.UsdSkel.BakeSkinning` over a single frame to capture the pose.
  4. Strip Skeleton / SkelAnimation / SkelBindingAPI / skel:* properties.
  5. Convert every Mesh's time-sampled `points` / `normals` / `extent` into
     static default values (no `.timeSamples`).
  6. Clear stage timeline metadata.
  7. Export to `baked/char_NN_*_baked.usdc`.
  8. Rewrite every absolute-path `asset` attribute in the exported file
     back to a project-relative path. `Usd.Stage.Flatten` resolves all
     references against the local filesystem, so without this pass the
     MDL / texture asset paths get baked as `D:/dev/.../Assets/...` on
     whichever machine ran the bake — a colleague who pulls the repo
     into a different drive then sees red error materials because Hydra
     can't resolve those paths.

Run from this folder with the project's Python (`pxr` must be importable):

    python bake_skinning.py
"""
import os
import time

from pxr import Gf, Sdf, Usd, UsdGeom, UsdSkel

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROPS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "Props"))
ANIMS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "Animations"))
BAKED_DIR = os.path.join(SCRIPT_DIR, "baked")

CHARACTERS = [
    {
        "prop_ref": "SK_bwom20008m4_ANI.usd",
        "anim_ref": "Draken_ani_bwom20008m4_ANI_00012_AnimSequence.usd",
        "skel_name": "SK_bwom20008m4_ANI",
    },
    {
        "prop_ref": "SK_cman20003m4_ANIv00001.usd",
        "anim_ref": "Draken_ani_cman20003m4_ANI_00008_AnimSequence.usd",
        "skel_name": "SK_cman20003m4_ANIv00001",
    },
    {
        "prop_ref": "SK_cwom0309m4_ANIv00004.usd",
        "anim_ref": "Draken_ani_cwom0309m4_ANI_00007_AnimSequence.usd",
        "skel_name": "SK_cwom0309m4_ANIv00004",
    },
    {
        "prop_ref": "SK_bman21092m4_ANIv00002.usd",
        "anim_ref": "Draken_ani_bman21092m4_ANI_00009_AnimSequence.usd",
        "skel_name": "SK_bman21092m4_ANIv00002",
    },
    {
        "prop_ref": "SK_bman21096m4_ANIv00002.usd",
        "anim_ref": "Draken_ani_bman21096m4_ANI_00010_AnimSequence.usd",
        "skel_name": "SK_bman21096m4_ANIv00002",
    },
    {
        "prop_ref": "SK_bman21108m4_ANIv00001.usd",
        "anim_ref": "Draken_ani_bman21108m4_ANI_00006_AnimSequence.usd",
        "skel_name": "SK_bman21108m4_ANIv00001",
    },
    {
        "prop_ref": "SK_bwom0324m4_ANIv00001.usd",
        "anim_ref": "Draken_ani_bwom0324m4_ANI_00004_AnimSequence.usd",
        "skel_name": "SK_bwom0324m4_ANIv00001",
    },
    {
        "prop_ref": "SK_bwom0325m4_ANI.usd",
        "anim_ref": "Draken_ani_bwom0325m4_ANI_00005_AnimSequence.usd",
        "skel_name": "SK_bwom0325m4_ANI",
    },
    {
        "prop_ref": "SK_bwom0328m4_ANIv00001.usd",
        "anim_ref": "Draken_ani_bwom0328m4_ANI_00011_AnimSequence.usd",
        "skel_name": "SK_bwom0328m4_ANIv00001",
    },
]

# We bake only this one frame from the source animation. Frame 0 is the
# natural sitting pose for these clips; bump it (e.g. 30, 60) if a later
# pose looks better.
FREEZE_FRAME = 0

# Attributes that BakeSkinning will write per-frame. We freeze each one to
# its value at FREEZE_FRAME and drop the time samples.
FREEZABLE_ATTRS = ("points", "normals", "extent")


def _strip_skel(stage: Usd.Stage) -> None:
    """Remove SkelRoot/Skeleton/SkelAnimation prims, SkelBindingAPI, and all
    skel:* / primvars:skel:* properties from a *flattened* stage. The Mesh's
    points are now baked, so any leftover UsdSkel data just causes Hydra to
    re-skin (or worse, conflict) and wastes VRAM."""
    prims_to_remove = []
    skel_root_to_xform = []

    for prim in stage.Traverse():
        type_name = prim.GetTypeName()

        if type_name in ("Skeleton", "SkelAnimation"):
            prims_to_remove.append(prim.GetPath())
            continue

        if type_name == "SkelRoot":
            skel_root_to_xform.append(prim.GetPath())

        if "SkelBindingAPI" in prim.GetAppliedSchemas():
            prim.RemoveAPI(UsdSkel.BindingAPI)

        for prop_name in [p.GetName() for p in prim.GetProperties()]:
            if prop_name.startswith("skel:") or prop_name.startswith("primvars:skel:"):
                prim.RemoveProperty(prop_name)

    for path in prims_to_remove:
        stage.RemovePrim(path)

    for path in skel_root_to_xform:
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid():
            prim.SetTypeName("Xform")


def _try_relativize(raw_path: str, anchor_dir: str) -> str:
    """Return a forward-slash relative path from ``anchor_dir`` if ``raw_path``
    is an absolute OS path that resolves to an existing file. Otherwise return
    ``raw_path`` unchanged.

    Why: ``Usd.Stage.Flatten`` resolves every reference/asset path to its
    absolute location on the machine that ran the bake, which then bakes a
    machine-specific path into the resulting ``.usdc``. When a colleague
    pulls those files into a project at a different drive/path, MDLs and
    textures fail to resolve and Hydra falls back to red error materials.

    We only rewrite paths that:
      * are absolute (``os.path.isabs``) and
      * point to a real file on disk.

    That deliberately ignores Unreal-style metadata paths like
    ``/Game/AXYZAssets/Materials/...`` (no drive, no actual file), which must
    stay verbatim because Kit treats them as plain strings.
    """
    try:
        if not raw_path:
            return raw_path
        if not os.path.isabs(raw_path):
            return raw_path
        if not os.path.isfile(raw_path):
            return raw_path
        rel = os.path.relpath(raw_path, anchor_dir).replace("\\", "/")
        return rel
    except Exception:
        return raw_path


def _relativize_layer_assets(usdc_path: str) -> int:
    """Open ``usdc_path`` and rewrite every ``asset`` / ``asset[]`` attribute
    whose value is an absolute path to a real file on disk into a relative
    path anchored at the ``.usdc``'s own directory. Saves in place. Returns
    the number of attributes touched.

    Run at the tail end of every bake so the produced files are portable
    (no machine- or user-specific drive prefixes baked into MDL / texture
    asset references). The same helper is reused by
    ``relativize_baked_paths.py`` to fix files that were baked before this
    pass existed.
    """
    anchor_dir = os.path.dirname(os.path.abspath(usdc_path))

    stage = Usd.Stage.Open(usdc_path)
    if stage is None:
        return 0

    touched = 0
    for prim in stage.Traverse():
        for attr in prim.GetAttributes():
            tn = attr.GetTypeName()
            if tn == Sdf.ValueTypeNames.Asset:
                v = attr.Get()
                if v is None:
                    continue
                new_path = _try_relativize(v.path, anchor_dir)
                if new_path != v.path:
                    attr.Set(Sdf.AssetPath(new_path))
                    touched += 1
            elif tn == Sdf.ValueTypeNames.AssetArray:
                arr = attr.Get()
                if arr is None:
                    continue
                changed = False
                new_arr = []
                for ap in arr:
                    new_path = _try_relativize(ap.path, anchor_dir)
                    if new_path != ap.path:
                        changed = True
                    new_arr.append(Sdf.AssetPath(new_path))
                if changed:
                    attr.Set(Sdf.AssetPathArray(new_arr))
                    touched += 1

    if touched:
        stage.GetRootLayer().Save()
    return touched


def _freeze_mesh_attrs(stage: Usd.Stage, freeze_time: float) -> int:
    """For every Mesh in the stage, sample `points`/`normals`/`extent` at
    `freeze_time`, write the sampled value as the static default, and clear
    time samples. Returns the number of attributes frozen."""
    frozen = 0
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        for attr_name in FREEZABLE_ATTRS:
            attr = prim.GetAttribute(attr_name)
            if not attr or not attr.IsValid():
                continue
            if not attr.GetTimeSamples():
                continue
            value = attr.Get(freeze_time)
            if value is None:
                continue
            attr.Clear()
            attr.Set(value)
            frozen += 1
    return frozen


def bake_one(char_data, index):
    prop_file = os.path.join(PROPS_DIR, char_data["prop_ref"]).replace("\\", "/")
    anim_file = os.path.join(ANIMS_DIR, char_data["anim_ref"]).replace("\\", "/")
    skel_name = char_data["skel_name"]
    anim_prim_name = char_data["anim_ref"].replace(".usd", "")
    out_file = os.path.join(
        BAKED_DIR, f"char_{index:02d}_{skel_name.replace('SK_', '')}_baked.usdc"
    ).replace("\\", "/")

    print(f"[{index:02d}] {char_data['prop_ref']} + {char_data['anim_ref']}")
    print(f"      -> {out_file}")

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)
    # We only need a single timecode for the bake call. Keep the stage
    # timeline tiny so BakeSkinning doesn't burn cycles on extra frames.
    stage.SetStartTimeCode(FREEZE_FRAME)
    stage.SetEndTimeCode(FREEZE_FRAME)
    stage.SetTimeCodesPerSecond(30)
    stage.SetFramesPerSecond(30)

    char = stage.DefinePrim("/Character", "Xform")
    char.GetReferences().AddReference(prop_file)
    char.GetReferences().AddReference(anim_file)
    stage.SetDefaultPrim(char)

    skel_root_path = f"/Character/{skel_name}"
    skel_root_prim = stage.GetPrimAtPath(skel_root_path)
    if not skel_root_prim or not skel_root_prim.IsValid():
        raise RuntimeError(f"SkelRoot not found at {skel_root_path}")

    binding = UsdSkel.BindingAPI.Apply(skel_root_prim)
    binding.CreateAnimationSourceRel().SetTargets(
        [Sdf.Path(f"/Character/{anim_prim_name}")]
    )

    interval = Gf.Interval(FREEZE_FRAME, FREEZE_FRAME)
    t0 = time.time()
    ok = UsdSkel.BakeSkinning(Usd.PrimRange(char), interval)
    dt = time.time() - t0
    if not ok:
        raise RuntimeError(
            f"UsdSkel.BakeSkinning returned False for {char_data['prop_ref']}"
        )
    print(f"      bake: {dt:.1f}s")

    flat_layer = stage.Flatten(addSourceFileComment=False)
    flat_stage = Usd.Stage.Open(flat_layer)
    _strip_skel(flat_stage)
    frozen = _freeze_mesh_attrs(flat_stage, FREEZE_FRAME)
    # Clear stage timeline metadata — the mesh is fully static now.
    flat_stage.ClearMetadata("startTimeCode")
    flat_stage.ClearMetadata("endTimeCode")
    flat_stage.ClearMetadata("timeCodesPerSecond")
    flat_stage.ClearMetadata("framesPerSecond")

    flat_layer.Export(out_file)

    # Flatten resolves every reference to its absolute path on the baking
    # machine; rewrite those back to project-relative paths so the file is
    # portable across users / drives.
    relativized = _relativize_layer_assets(out_file)

    size_mb = os.path.getsize(out_file) / (1024 * 1024)
    print(
        f"      froze {frozen} mesh attrs, "
        f"relativized {relativized} asset paths, wrote {size_mb:.2f} MB"
    )


def main():
    os.makedirs(BAKED_DIR, exist_ok=True)
    print(f"Output dir: {BAKED_DIR}")
    print(f"Freeze frame: {FREEZE_FRAME} (single static pose)\n")

    for i, char in enumerate(CHARACTERS, start=1):
        bake_one(char, i)

    print(f"\nDone. Baked {len(CHARACTERS)} static characters into {BAKED_DIR}")


if __name__ == "__main__":
    main()
