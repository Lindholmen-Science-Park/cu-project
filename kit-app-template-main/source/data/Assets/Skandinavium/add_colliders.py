"""
Script to add physics colliders to all mesh-reference prims in Skandinavium.usda.

Pattern applied (matching manually-added colliders):
  - Adds PhysicsCollisionAPI, PhysxCollisionAPI, PhysxTriangleMeshCollisionAPI,
    PhysicsMeshCollisionAPI to apiSchemas
  - Adds physics:approximation = "none" and physics:collisionEnabled = 1

Only targets `def "Name" (` prims with `prepend references = @Assets/...@`.
Skips: def Xform, def Material, def Shader, over blocks, already-collided prims.
"""

import re
import sys
import shutil
from pathlib import Path

PHYSICS_APIS = [
    '"PhysicsCollisionAPI"',
    '"PhysxCollisionAPI"',
    '"PhysxTriangleMeshCollisionAPI"',
    '"PhysicsMeshCollisionAPI"',
]

PHYSICS_PROPS = [
    'uniform token physics:approximation = "none"',
    'bool physics:collisionEnabled = 1',
]

# Regex to match a `def "SomeName" (` line (no type keyword like Xform/Material/Shader)
DEF_PRIM_RE = re.compile(r'^(\s*)def\s+"([^"]+)"\s*\(')

# Regex to match `def Xform`, `def Material`, `def Shader`, etc.
DEF_TYPED_RE = re.compile(r'^\s*def\s+\w+\s+"')

# Regex to match `over "..."` blocks
OVER_RE = re.compile(r'^\s*over\s+"')

# Regex for apiSchemas line
API_SCHEMAS_RE = re.compile(r'^(\s*)prepend\s+apiSchemas\s*=\s*\[([^\]]*)\]')

# Regex for references line
REFERENCES_RE = re.compile(r'^\s*prepend\s+references\s*=\s*@Assets/')


def process_file(filepath: Path, dry_run: bool = False):
    lines = filepath.read_text(encoding='utf-8').splitlines(keepends=True)

    new_lines = []
    i = 0
    modified_count = 0
    skipped_count = 0

    while i < len(lines):
        line = lines[i]

        # Check for a `def "Name" (` line (untyped def)
        m = DEF_PRIM_RE.match(line)
        if m and not DEF_TYPED_RE.match(line):
            indent = m.group(1)
            prim_name = m.group(2)
            inner_indent = indent + "    "

            # Collect the metadata block (from `def "..." (` to the closing `)`)
            meta_start = i
            meta_lines = [line]
            i += 1

            has_references = False
            has_physics = False
            api_schemas_idx = None  # index within meta_lines
            api_schemas_content = None

            # Walk forward through the metadata block until we find `)`
            while i < len(lines):
                mline = lines[i]
                meta_lines.append(mline)

                if REFERENCES_RE.match(mline):
                    has_references = True

                if 'PhysicsCollisionAPI' in mline:
                    has_physics = True

                am = API_SCHEMAS_RE.match(mline)
                if am:
                    api_schemas_idx = len(meta_lines) - 1
                    api_schemas_content = am.group(2)

                # Check if this line closes the metadata with `)`
                if mline.strip() == ')':
                    i += 1
                    break

                i += 1

            # Now we should be at the `{` line
            if not has_references or has_physics:
                # Not a target prim or already has physics - emit as-is
                if has_physics and has_references:
                    skipped_count += 1
                new_lines.extend(meta_lines)
                continue

            # This prim needs colliders!
            modified_count += 1

            # Modify apiSchemas
            if api_schemas_idx is not None:
                # Existing apiSchemas - append physics APIs
                existing = api_schemas_content.strip()
                if existing:
                    new_schemas = existing + ", " + ", ".join(PHYSICS_APIS)
                else:
                    new_schemas = ", ".join(PHYSICS_APIS)
                meta_lines[api_schemas_idx] = (
                    f"{inner_indent}prepend apiSchemas = [{new_schemas}]\n"
                )
            else:
                # No apiSchemas line - insert one before the references line
                schemas_line = (
                    f"{inner_indent}prepend apiSchemas = "
                    f"[{', '.join(PHYSICS_APIS)}]\n"
                )
                # Find the references line in meta_lines and insert before it
                ref_idx = None
                for j, ml in enumerate(meta_lines):
                    if REFERENCES_RE.match(ml):
                        ref_idx = j
                        break
                if ref_idx is not None:
                    meta_lines.insert(ref_idx, schemas_line)
                else:
                    # Fallback: insert after the def line
                    meta_lines.insert(1, schemas_line)

            new_lines.extend(meta_lines)

            # Now emit the `{` line and inject physics properties after it
            if i < len(lines) and lines[i].strip() == '{':
                new_lines.append(lines[i])
                i += 1

                # Insert physics properties right after `{`
                # Find the first real property line to determine body indentation
                body_indent = inner_indent
                for prop in PHYSICS_PROPS:
                    new_lines.append(f"{body_indent}{prop}\n")
            continue

        new_lines.append(line)
        i += 1

    if dry_run:
        print(f"[DRY RUN] Would modify {modified_count} prims "
              f"({skipped_count} already have colliders)")
        return modified_count

    # Write output
    backup_path = filepath.with_suffix('.usda.bak')
    shutil.copy2(filepath, backup_path)
    print(f"Backup saved to: {backup_path}")

    filepath.write_text(''.join(new_lines), encoding='utf-8')
    print(f"Modified {modified_count} prims "
          f"({skipped_count} already had colliders)")
    return modified_count


if __name__ == '__main__':
    target = Path(__file__).parent / 'Skandinavium.usda'

    dry_run = '--dry-run' in sys.argv

    if not target.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    print(f"Processing: {target}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    count = process_file(target, dry_run=dry_run)

    if count == 0:
        print("No prims needed modification.")
