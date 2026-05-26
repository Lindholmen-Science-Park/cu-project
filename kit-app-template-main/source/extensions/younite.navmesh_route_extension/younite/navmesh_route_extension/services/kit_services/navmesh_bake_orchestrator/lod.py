"""Stadium LOD coordination for NavMesh bakes.

Bird-eye + light LOD drops interior geometry; we temporarily force full LOD
so the baker sees walkable interiors, then restore the previous LOD.
"""

from __future__ import annotations

from typing import Optional


async def await_lod(target: str, *, deadline_sec: float) -> bool:
    import time

    import carb
    import omni.kit.app as kit_app

    deadline = time.monotonic() + deadline_sec
    settings = carb.settings.get_settings()
    app = kit_app.get_app()
    while time.monotonic() < deadline:
        cur = str(settings.get("/younite/stadium/currentLod") or "").strip()
        if cur == target:
            return True
        await app.next_update_async()
    return False


async def ensure_full_lod_for_bake() -> Optional[str]:
    """If bird-eye + light LOD, switch to full and wait.

    Returns the LOD value to restore after the bake (``"light"``) or
    ``None`` when no switch was needed / possible.
    """
    try:
        import carb

        settings = carb.settings.get_settings()

        view_type = str(settings.get("/younite/camera/viewType") or "").strip()
        if view_type != "birdEye":
            return None

        current_lod = str(settings.get("/younite/stadium/currentLod") or "").strip()
        if current_lod != "light":
            return None

        try:
            import carb.eventdispatcher as _ed

            _ed.get_eventdispatcher().dispatch_event(
                "stadiumLodToggle", {"lod": "full"}
            )
        except Exception as exc:
            print(f"[BAKE_ORCH] failed to dispatch stadiumLodToggle (full): {exc}")
            return None

        ok = await await_lod("full", deadline_sec=10.0)
        if not ok:
            print("[BAKE_ORCH] timed out waiting for full LOD before bake — proceeding anyway")
        else:
            print("[BAKE_ORCH] LOD switched to full for bake (will restore to light)")
        return "light"
    except Exception as exc:
        print(f"[BAKE_ORCH] ensure_full_lod_for_bake error: {exc}")
        return None


async def restore_lod(target_lod: str) -> None:
    try:
        import carb.eventdispatcher as _ed

        _ed.get_eventdispatcher().dispatch_event(
            "stadiumLodToggle", {"lod": target_lod}
        )
        ok = await await_lod(target_lod, deadline_sec=10.0)
        if not ok:
            print(f"[BAKE_ORCH] timed out waiting for LOD restore to '{target_lod}'")
        else:
            print(f"[BAKE_ORCH] LOD restored to '{target_lod}' after bake")
    except Exception as exc:
        print(f"[BAKE_ORCH] failed to restore LOD '{target_lod}': {exc}")
