"""
Wet-ground texture overrides for paved surfaces (roads, concrete, cobblestone).

Darkened, saturated textures simulate salted wet pavement as seen in Nordic
winters.  The service tracks *reasons* why the ground should look wet —
currently ``"weather"`` (rain / snow active) and ``"season"`` (winter).
Textures are cleared only when **all** reasons are removed.

Called from:
  - sky_service.py   → set_wet("weather", True/False) on rain/snow toggle
  - extension.py     → set_wet("season", True/False) on winter toggle
"""

from __future__ import annotations

import os
import re
from typing import Optional

_WET_PAVED_MATERIALS: dict[str, str] = {
    "mat_Asfalt":       "Asfalt_winter_frost.jpg",
    "mat_Betong":       "Betong_winter_frost.jpg",
    "mat_Betongplatta": "Betongplatta_winter_frost.jpg",
    "mat_VG_Kantsten":  "VG_Kantsten_winter_frost.jpg",
    "mat_Smaagatsten":  "Smaagatsten_winter_frost.jpg",
    "mat_Storgatsten":  "Storgatsten_winter_frost.jpg",
    "mat_Kullersten":   "Kullersten_winter_frost.jpg",
    "mat_Natursten":    "Natursten_winter_frost.jpg",
    "mat_SF_sten":      "SF_sten_winter_frost.jpg",
    "mat_Sinusplatta":  "Sinusplatta_winter_frost.jpg",
    "mat_Trappa":       "Trappa_winter_frost.jpg",
    "mat_Mur":          "Mur_winter_frost.jpg",
}

_PAVED_BASE_NAMES: set[str] = set(_WET_PAVED_MATERIALS.keys())
_SHADER_NAMES = ("usduvtexture1", "Image_Texture")

_wet_reasons: set[str] = set()
_paved_shader_paths: list[tuple[str, str]] | None = None
_original_textures: dict[str, str] = {}
_wet_dir: str | None = None


def _match_base_material(mat_prim_name: str) -> Optional[str]:
    if mat_prim_name in _PAVED_BASE_NAMES:
        return mat_prim_name
    m = re.match(r"^(.+?)_\d+$", mat_prim_name)
    if m and m.group(1) in _PAVED_BASE_NAMES:
        return m.group(1)
    return None


def _discover(stage) -> list[tuple[str, str]]:
    global _paved_shader_paths
    if _paved_shader_paths is not None:
        return _paved_shader_paths

    _paved_shader_paths = []
    for prim in stage.Traverse():
        path_str = str(prim.GetPath())
        if prim.GetName() not in _SHADER_NAMES:
            continue
        parts = path_str.rsplit("/", 2)
        if len(parts) < 2:
            continue
        base = _match_base_material(parts[-2])
        if base is not None:
            _paved_shader_paths.append((path_str, base))
            attr = prim.GetAttribute("inputs:file")
            if attr:
                val = attr.Get()
                if val:
                    _original_textures[path_str] = str(val.resolvedPath or val.path)

    print(f"[wet_ground] discovered {len(_paved_shader_paths)} paved shader prims "
          f"({len(_original_textures)} original textures cached)")
    return _paved_shader_paths


def _resolve_dir(stage) -> str:
    global _wet_dir
    if _wet_dir is None:
        root_layer = stage.GetRootLayer()
        root_dir = os.path.dirname(root_layer.realPath)
        data_dir = os.path.normpath(os.path.join(root_dir, ".."))
        _wet_dir = os.path.normpath(
            os.path.join(data_dir, "Assets", "SeasonalTextures", "Frost")
        )
    return _wet_dir


def _resolve_textures(stage) -> dict[str, str]:
    d = _resolve_dir(stage)
    result: dict[str, str] = {}
    for mat, fname in _WET_PAVED_MATERIALS.items():
        full = os.path.join(d, fname)
        if os.path.isfile(full):
            result[mat] = full
    return result


def _apply(stage) -> None:
    from pxr import Usd, Sdf

    paths = _discover(stage)
    if not paths:
        return

    tex_map = _resolve_textures(stage)
    if not tex_map:
        print("[wet_ground] no wet textures found — run generate_frost_textures.py")
        return

    session = stage.GetSessionLayer()
    count = 0
    with Sdf.ChangeBlock():
        with Usd.EditContext(stage, session):
            for prim_path, base_mat in paths:
                tex = tex_map.get(base_mat)
                if not tex:
                    continue
                prim = stage.GetPrimAtPath(prim_path)
                if not prim:
                    continue
                attr = prim.GetAttribute("inputs:file")
                if not attr:
                    continue
                attr.Set(Sdf.AssetPath(tex))
                count += 1

    print(f"[wet_ground] applied wet textures to {count} paved surfaces")


def _clear(stage) -> None:
    """Restore original textures instead of clearing the session-layer override.
    Setting the original path explicitly avoids the neon-blue flash that occurs
    when attr.Clear() leaves a gap for Hydra to show its missing-texture color."""
    from pxr import Usd, Sdf

    paths = _discover(stage)
    if not paths:
        return

    session = stage.GetSessionLayer()
    restored = 0
    cleared = 0
    with Sdf.ChangeBlock():
        with Usd.EditContext(stage, session):
            for prim_path, _ in paths:
                prim = stage.GetPrimAtPath(prim_path)
                if not prim:
                    continue
                attr = prim.GetAttribute("inputs:file")
                if not attr:
                    continue
                original = _original_textures.get(prim_path)
                if original:
                    attr.Set(Sdf.AssetPath(original))
                    restored += 1
                else:
                    attr.Clear()
                    cleared += 1

    if restored or cleared:
        print(f"[wet_ground] restored {restored} original textures"
              f"{f', cleared {cleared} (no cached original)' if cleared else ''}")


def set_wet(reason: str, active: bool, stage=None) -> None:
    """Add or remove a reason for wet ground.  Applies/clears textures only
    when the overall state changes (any reason → apply, no reasons → clear)."""
    was_wet = bool(_wet_reasons)

    if active:
        _wet_reasons.add(reason)
    else:
        _wet_reasons.discard(reason)

    is_wet = bool(_wet_reasons)

    if is_wet == was_wet:
        return

    if stage is None:
        try:
            import omni.usd
            stage = omni.usd.get_context().get_stage()
        except Exception:
            return
    if not stage:
        return

    if is_wet:
        _apply(stage)
    else:
        _clear(stage)


def invalidate_cache() -> None:
    global _paved_shader_paths, _wet_dir
    _paved_shader_paths = None
    _wet_dir = None
    _original_textures.clear()
    _wet_reasons.clear()
