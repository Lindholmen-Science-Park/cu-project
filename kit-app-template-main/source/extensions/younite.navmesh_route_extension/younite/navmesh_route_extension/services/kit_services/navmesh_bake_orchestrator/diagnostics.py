"""Post-bake NavMesh diagnostics."""

from __future__ import annotations


def log_baked_navmesh_areas() -> None:
    """Diagnostic: print what areas the baked navmesh actually contains."""
    try:
        import omni.anim.navigation.core as nav_module

        inav = nav_module.acquire_interface()
        if not inav:
            return
        nm = inav.get_navmesh()
        if not nm:
            return
        count = nm.get_area_count()
        names = []
        for i in range(count):
            n = nm.get_area_name(i)
            names.append(n)
        print(f"[BAKE_ORCH] Baked navmesh has {count} area(s): {names}")
    except Exception as exc:
        print(f"[BAKE_ORCH] navmesh area diagnostic failed: {exc}")
