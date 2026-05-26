"""Generate sitting character wrapper .usda files.

Each wrapper now points at a **pre-baked** mesh asset (produced by
`bake_skinning.py`) rather than composing the live UsdSkel rig + animation
at runtime. The baked file is a plain Xform/Mesh with time-sampled
`points`/`normals`/`extent` — no Skeleton, no SkelBindingAPI — so it can
safely be marked `instanceable = true`.

That's the whole point of the bake: UsdSkel skinning does not survive
scene-graph instance boundaries in Omniverse RTX (every copy renders in
T-pose, see prior debugging history), but a regular animated Mesh does.
Hydra now uploads each character variant's geometry once and shares it
across all ~11.5k seats.

Wrapper shape:

    def Xform "Character" (
        instanceable = true
        prepend references = @../baked/char_NN_*_baked.usdc@
    ) {}
"""
import os

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

BAKED_DIR = "../baked"


def generate_wrapper(index, char_data):
    short = char_data["skel_name"].replace("SK_", "")
    baked_file = f"char_{index:02d}_{short}_baked.usdc"
    return (
        f"#usda 1.0\n"
        f"(\n"
        f'    defaultPrim = "Character"\n'
        f")\n"
        f"\n"
        f'def Xform "Character" (\n'
        f"    instanceable = true\n"
        f"    prepend references = @{BAKED_DIR}/{baked_file}@\n"
        f")\n"
        f"{{\n"
        f"}}\n"
    )


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for i, char in enumerate(CHARACTERS, start=1):
        short = char["skel_name"].replace("SK_", "")
        filename = f"char_{i:02d}_{short}.usda"
        filepath = os.path.join(script_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(generate_wrapper(i, char))
        print(f"  Created {filename}")
    print(f"\nGenerated {len(CHARACTERS)} character files in {script_dir}")


if __name__ == "__main__":
    main()
