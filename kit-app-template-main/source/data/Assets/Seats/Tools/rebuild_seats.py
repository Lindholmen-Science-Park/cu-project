"""Full seat rebuild pipeline — one command to regenerate everything.

Runs four steps in order:
  1. extract_cad_seats     — parse DXF → extracted_seats_with_rows.json (CAD-style WC / R* wheelchair rows)
  2. generate_instancer    — build PointInstancer USD (+ availability + variant config)
  3. create_lookup         — compute world-space seats_lookup.json from composed scene
  4. build_seat_hierarchy  — compact section/row/seat tree for the web dropdowns

Optional **between** steps 1 and 2: run ``postprocess_wheelchair_wc_to_row6.py``
to normalize wheelchair rows to ticket-style row ``6`` (see
``.cursor/rules/topics/seat-navigation.mdc`` § Step 1a). ``rebuild_seats.py`` does
not invoke it automatically.

Usage:
    python rebuild_seats.py              # outputs .usda (text)
    python rebuild_seats.py --usdc       # outputs .usdc (binary, smaller/faster)

Requires: ezdxf, numpy, pxr (OpenUSD)
"""

import argparse
import sys
import time


def run_step(label, fn):
    print(f"\n{'=' * 60}")
    print(f"  STEP: {label}")
    print(f"{'=' * 60}\n")
    t0 = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - t0
    print(f"\n  [{label}] done in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="Full seat rebuild: extract → instancer → lookup")
    parser.add_argument("--usdc", action="store_true",
                        help="Output binary .usdc instead of text .usda")
    args = parser.parse_args()

    # Step 1 — Extract seat data from DXF
    import extract_cad_seats
    run_step("Extract CAD seats", extract_cad_seats.main)

    # Step 2 — Generate instanced USD
    # Patch sys.argv so generate_instancer's argparse picks up --usdc
    saved_argv = sys.argv
    sys.argv = ["generate_instancer.py"]
    if args.usdc:
        sys.argv.append("--usdc")
    try:
        import generate_instancer
        run_step("Generate instancer", generate_instancer.main)
    finally:
        sys.argv = saved_argv

    # Step 3 — Build world-space lookup
    import create_lookup
    run_step("Create world-space lookup", create_lookup.main)

    # Step 4 — Build the compact section/row/seat tree consumed by the web
    # seat-finder dropdowns (Section -> Row -> Seat cascade).
    import build_seat_hierarchy
    run_step("Build seat hierarchy (web)", build_seat_hierarchy.main)

    print(f"\n{'=' * 60}")
    print("  ALL DONE — seats fully rebuilt")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
