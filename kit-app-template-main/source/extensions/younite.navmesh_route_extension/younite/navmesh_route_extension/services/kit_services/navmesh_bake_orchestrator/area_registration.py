"""Sync provider area definitions into root ``customLayerData`` for the baker."""

from __future__ import annotations

from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .protocol import NavMeshAreaProvider


def sync_provider_areas_to_custom_layer(
    providers: Dict[str, "NavMeshAreaProvider"],
) -> None:
    """Merge provider ``get_area_definitions`` into ``navmeshSettings.areas``."""
    import omni.usd
    from pxr import Gf

    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        return

    root_layer = stage.GetRootLayer()
    custom_data = dict(root_layer.customLayerData)
    nav_settings = dict(custom_data.get("navmeshSettings", {}))
    raw_areas = nav_settings.get("areas", {})
    areas = dict(raw_areas) if raw_areas else {}

    existing_names: set = set()
    for v in areas.values():
        try:
            name = v.get("areaName") if hasattr(v, "get") else None
            if name:
                existing_names.add(str(name))
        except Exception:
            pass

    next_id = max((int(k) for k in areas if str(k).isdigit()), default=-1) + 1

    provider_defs: list = []
    for provider in providers.values():
        if hasattr(provider, "get_area_definitions"):
            try:
                provider_defs.extend(provider.get_area_definitions())
            except Exception as exc:
                print(
                    f"[BAKE_ORCH] get_area_definitions failed for "
                    f"'{provider.name}': {exc}"
                )

    added: List[str] = []
    for defn in provider_defs:
        name = defn.get("areaName")
        if not name or name in existing_names:
            continue
        raw_color = defn.get("color", [0.5, 0.5, 0.5])
        if isinstance(raw_color, (list, tuple)):
            color = Gf.Vec3f(
                float(raw_color[0]), float(raw_color[1]), float(raw_color[2])
            )
        else:
            color = raw_color
        areas[str(next_id)] = {
            "areaName": str(name),
            "color": color,
            "defaultCost": float(defn.get("defaultCost", 1.0)),
        }
        existing_names.add(name)
        added.append(name)
        next_id += 1

    if added:
        nav_settings["areas"] = areas
        custom_data["navmeshSettings"] = nav_settings
        try:
            root_layer.customLayerData = custom_data
        except Exception as exc:
            print(f"[BAKE_ORCH] customLayerData write failed: {exc}")

        print(
            f"[BAKE_ORCH] ⚠ {len(added)} area(s) missing from main_scene.usda: "
            f"{added}  — add them to customLayerData.navmeshSettings.areas, "
            f"save, and reload for the baker to recognise them"
        )
    else:
        print(
            f"[BAKE_ORCH] All {len(existing_names)} area(s) present in customLayerData — OK"
        )
