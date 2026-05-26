from __future__ import annotations

from typing import Optional, Tuple


# Canonical prim paths for this app (scenes are expected to follow these conventions).
WORLD_ROOT_PATH = "/World"

PLAYER_CHARACTER_NAME = "PlayerCharacter"
PLAYER_CHARACTER_PATH = f"{WORLD_ROOT_PATH}/{PLAYER_CHARACTER_NAME}"

PLAYER_FIRST_PERSON_CAMERA_NAME = "first_person_camera"
PLAYER_FIRST_PERSON_CAMERA_PATH = f"{PLAYER_CHARACTER_PATH}/{PLAYER_FIRST_PERSON_CAMERA_NAME}"

DEFAULT_PLAYER_SPAWNPOINT_NAME = "PlayerSpawnPoint_02"

_DEFAULT_VIEW_TYPE_SETTING = "/younite/camera/defaultViewType"
_SPAWNPOINTS_FOR_VIEW = {
    "firstPerson": "PlayerSpawnPoint_01",
    "birdEye": "PlayerSpawnPoint_02",
}


def get_default_view_type() -> str:
    """Read the configured default view type from carb settings, falling back to 'firstPerson'."""
    try:
        import carb
        val = carb.settings.get_settings().get(_DEFAULT_VIEW_TYPE_SETTING)
        if val and str(val).strip() in ("firstPerson", "birdEye"):
            return str(val).strip()
    except Exception:
        pass
    return "firstPerson"


def default_spawnpoint_for_view(view_type: str) -> str:
    return _SPAWNPOINTS_FOR_VIEW.get(view_type, DEFAULT_PLAYER_SPAWNPOINT_NAME)


def spawn_point_path(spawn_point_name: str) -> str:
    return f"{WORLD_ROOT_PATH}/{str(spawn_point_name).strip('/')}"


def player_camera_path(
    *,
    player_path: str = PLAYER_CHARACTER_PATH,
    camera_name: str = PLAYER_FIRST_PERSON_CAMERA_NAME,
) -> str:
    return f"{str(player_path).rstrip('/')}/{str(camera_name).lstrip('/')}"


def get_valid_prim(stage, path: str):
    """Return prim at path if valid, else None."""
    try:
        prim = stage.GetPrimAtPath(str(path))
        if prim and prim.IsValid():
            return prim
    except Exception:
        pass
    return None


def find_spawn_point_prim(stage, spawn_point_name: str):
    """
    Find a spawn point Xform prim under /World.

    - First: `/World/<name>`
    - Fallback: traverse descendants of `/World` and match by prim name or displayName.
    """
    try:
        from pxr import Usd, UsdGeom
    except Exception:
        Usd = None
        UsdGeom = None

    name = str(spawn_point_name or "").strip()
    if not name or not stage:
        return None, None

    direct_path = spawn_point_path(name)
    prim = get_valid_prim(stage, direct_path)
    if prim and (UsdGeom is None or prim.IsA(UsdGeom.Xform)):
        return prim, direct_path

    # Fallback: search below /World only (supports grouping under /World/SpawnPoints/...).
    world = get_valid_prim(stage, WORLD_ROOT_PATH)
    if not world or (Usd is None):
        return None, None

    try:
        # PrimRange over /World subtree is cheaper/safer than stage.Traverse().
        for p in Usd.PrimRange(world):
            try:
                if not (p and p.IsValid()):
                    continue
                if UsdGeom is not None and (not p.IsA(UsdGeom.Xform)):
                    continue
                if p.GetName() == name:
                    return p, str(p.GetPath())
                dn = p.GetDisplayName() or p.GetMetadata("displayName")
                if dn == name:
                    return p, str(p.GetPath())
            except Exception:
                continue
    except Exception:
        pass

    return None, None

