"""
Script to selectively remove physics colliders from decorative/non-structural
prims in Skandinavium.usda, keeping colliders only on gameplay-relevant prims
(floors, walls, ceilings, stairs, doors, facades, railings, structural elements).

This reverses the add_colliders.py operation for prims matching removal criteria.

Removal targets:
  - All P_ (props: chairs, tables, lights, signs, fridges, shelves, bars, etc.)
  - All MT_ (trees / plants)
  - Prims with names containing decorative keywords (Chair, Kiosk, Screen,
    Banner, Sign, Lamp, Light, Hinge, Handle, Fridge, Cabinet, Garbage,
    Booth, MCD, Grate, Grid, Pipe, Insulation, Bollard, etc.)

Keeps colliders on:
  - Walls, floors, ceilings, stairs, doors, windows, facades, railings,
    pillars, ramps, slabs, beams, bleacher surfaces, counters, panels,
    tiles, thresholds, entrances, terrain/landscape bases, merged meshes, etc.
"""

import re
import sys
import shutil
from pathlib import Path

PHYSICS_APIS = {
    '"PhysicsCollisionAPI"',
    '"PhysxCollisionAPI"',
    '"PhysxTriangleMeshCollisionAPI"',
    '"PhysicsMeshCollisionAPI"',
}

PHYSICS_PROP_PATTERNS = [
    re.compile(r'^\s*uniform\s+token\s+physics:approximation\s*='),
    re.compile(r'^\s*bool\s+physics:collisionEnabled\s*='),
]

# --- Removal criteria ---

# Prefixes that are entirely decorative/props
REMOVE_PREFIXES = ('P_', 'MT_')

# Keywords in prim name that indicate decorative/non-structural
# (case-insensitive matching)
REMOVE_KEYWORDS = [
    'Chair',
    'Kiosk',
    'Screen',
    'Banner',
    'Sign',
    'Lamp',
    'Light',
    'Hinge',
    'Handle',
    'Fridge',
    'Cabinet',
    'Shelf',       # not matched by other rules
    'Grate',
    'Grid',
    'MCD',
    'Booth',
    'Garbage',
    'Bollard',
    'Pipe',
    'Insulation',
    '_Various',
    '_Lines',
    'Emissive',
    'Orange_Box',
    'ReklamSkylt',
    'Pinus',
    'Water_Context',
    'Sofa',
    'Trashcan',
    'Popcorn',
    'Espresso',
    'Monitor',
    'Mixer',
    'Icemachine',
    'Fire',        # fire extinguisher props
    'Glass',       # glass facades, windows, panels - not needed for collision
    'Window',      # window frames and glass windows
    'Roof',        # roof elements - not reachable in gameplay
    'Ceiling',     # ceilings - not needed for ground-level gameplay
    'Raster',      # orange extension raster elements - decorative
]

# Specific prim name prefixes to remove (startswith match)
REMOVE_NAME_PREFIXES = [
    'SC_Metal_Facade_Exterior',
]

REMOVE_KEYWORDS_LOWER = [kw.lower() for kw in REMOVE_KEYWORDS]

# Regex to match a `def "SomeName" (` line (no type keyword like Xform/Material/Shader)
DEF_PRIM_RE = re.compile(r'^(\s*)def\s+"([^"]+)"\s*\(')
DEF_TYPED_RE = re.compile(r'^\s*def\s+\w+\s+"')
OVER_RE = re.compile(r'^\s*over\s+"')
API_SCHEMAS_RE = re.compile(r'^(\s*)prepend\s+apiSchemas\s*=\s*\[([^\]]*)\]')
REFERENCES_RE = re.compile(r'^\s*prepend\s+references\s*=\s*@Assets/')


def should_remove_collider(prim_name: str) -> bool:
    """Return True if colliders should be removed from this prim."""
    if prim_name.startswith(REMOVE_PREFIXES):
        return True
    for prefix in REMOVE_NAME_PREFIXES:
        if prim_name.startswith(prefix):
            return True
    name_lower = prim_name.lower()
    for kw in REMOVE_KEYWORDS_LOWER:
        if kw in name_lower:
            return True
    return False


def strip_physics_from_api_schemas(api_line_content: str, indent: str) -> str | None:
    """Remove physics APIs from an apiSchemas line.

    Returns the cleaned line, or None if the line should be removed entirely
    (i.e., no APIs remain).
    """
    # Parse existing APIs
    apis = [a.strip() for a in api_line_content.split(',') if a.strip()]
    remaining = [a for a in apis if a not in PHYSICS_APIS]

    if not remaining:
        return None
    return f"{indent}prepend apiSchemas = [{', '.join(remaining)}]\n"


def is_physics_property(line: str) -> bool:
    """Check if a line is a physics property we should remove."""
    for pat in PHYSICS_PROP_PATTERNS:
        if pat.match(line):
            return True
    return False


def process_file(filepath: Path, dry_run: bool = False):
    lines = filepath.read_text(encoding='utf-8').splitlines(keepends=True)

    new_lines = []
    i = 0
    removed_count = 0
    kept_count = 0
    no_collider_count = 0

    while i < len(lines):
        line = lines[i]

        m = DEF_PRIM_RE.match(line)
        if m and not DEF_TYPED_RE.match(line):
            indent = m.group(1)
            prim_name = m.group(2)
            inner_indent = indent + "    "

            # Collect the metadata block
            meta_start = i
            meta_lines = [line]
            i += 1

            has_references = False
            has_physics = False
            api_schemas_idx = None
            api_schemas_content = None

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

                if mline.strip() == ')':
                    i += 1
                    break
                i += 1

            if not has_references or not has_physics:
                # Not a collider prim - emit as-is
                if not has_physics:
                    no_collider_count += 1
                new_lines.extend(meta_lines)
                continue

            # This prim has colliders - check if we should remove them
            if not should_remove_collider(prim_name):
                kept_count += 1
                new_lines.extend(meta_lines)
                continue

            # Remove colliders from this prim
            removed_count += 1

            # Clean apiSchemas line
            if api_schemas_idx is not None:
                cleaned = strip_physics_from_api_schemas(
                    api_schemas_content, inner_indent
                )
                if cleaned is None:
                    # Remove the apiSchemas line entirely
                    del meta_lines[api_schemas_idx]
                else:
                    meta_lines[api_schemas_idx] = cleaned

            new_lines.extend(meta_lines)

            # Now handle the body: remove physics property lines inside `{ ... }`
            if i < len(lines) and lines[i].strip() == '{':
                new_lines.append(lines[i])
                i += 1

                # Track brace depth to find all lines in this prim's body
                depth = 1
                while i < len(lines) and depth > 0:
                    body_line = lines[i]
                    stripped = body_line.strip()

                    if stripped == '{':
                        depth += 1
                    elif stripped == '}':
                        depth -= 1

                    # Only remove physics properties at the top level of this prim (depth 1)
                    if depth >= 1 and is_physics_property(body_line):
                        i += 1  # skip this line
                        continue

                    new_lines.append(body_line)
                    i += 1

                # Continue normal processing from here
            continue

        new_lines.append(line)
        i += 1

    print(f"Colliders removed from: {removed_count} prims")
    print(f"Colliders kept on:      {kept_count} prims")
    print(f"Prims without colliders: {no_collider_count}")

    if dry_run:
        print(f"\n[DRY RUN] No changes written.")

        # Show breakdown of what would be removed
        print(f"\n--- Removal breakdown ---")
        from collections import Counter
        removal_reasons = Counter()
        text = filepath.read_text(encoding='utf-8')
        pattern = r'def "([^"]+)"\s*\(\s*\n\s*prepend apiSchemas\s*=\s*\[[^\]]*PhysicsCollisionAPI[^\]]*\]'
        for name in re.findall(pattern, text):
            if should_remove_collider(name):
                if name.startswith(REMOVE_PREFIXES):
                    removal_reasons[f"prefix:{name[:2]}"] += 1
                else:
                    name_lower = name.lower()
                    for kw in REMOVE_KEYWORDS_LOWER:
                        if kw in name_lower:
                            removal_reasons[f"keyword:{kw}"] += 1
                            break
        for reason, count in removal_reasons.most_common():
            print(f"  {count:4d} prims matched by {reason}")

        return removed_count

    # Write output
    backup_path = filepath.with_suffix('.usda.collider_bak')
    shutil.copy2(filepath, backup_path)
    print(f"\nBackup saved to: {backup_path}")

    filepath.write_text(''.join(new_lines), encoding='utf-8')
    print("Changes written successfully.")
    return removed_count


if __name__ == '__main__':
    target = Path(__file__).parent / 'Skandinavium.usda'

    dry_run = '--dry-run' in sys.argv

    if not target.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    print(f"Processing: {target}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    count = process_file(target, dry_run=dry_run)

    if count == 0:
        print("\nNo prims matched removal criteria.")
