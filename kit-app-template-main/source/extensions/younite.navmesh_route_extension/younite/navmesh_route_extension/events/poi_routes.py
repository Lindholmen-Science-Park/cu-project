"""Route measure toggle, bulk POI/exit routing, generic POI teleport."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Dict

from .poi_state import discover_pois, enrich_results, find_data_dir
from .wiring import NavmeshWireContext

_POI_ARRIVAL_DATA_FILES = (
    "restroom_data.json",
    "quiet_zone_data.json",
    "exit_data.json",
    "elevator_data.json",
    "kiosk_data.json",
    "ticket_office_data.json",
)


def _prim_leaf(prim_path: str) -> str:
    return prim_path.rsplit("/", 1)[-1] if prim_path else ""


def _arrival_label_for_prim_path(prim_path: str) -> Dict[str, str]:
    """Human-readable CU arrival label (and optional i18n key) for ``poiTeleportResult``."""
    leaf = _prim_leaf(prim_path)
    label = leaf or "location"
    i18n_key = ""
    data_dir = find_data_dir()
    if not data_dir:
        return {"arrivalLabel": label, "arrivalLabelI18nKey": i18n_key}

    if "/NavShortcuts/" in prim_path:
        shortcuts_path = os.path.join(data_dir, "shortcuts.json")
        try:
            with open(shortcuts_path, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
            for group in raw.get("groups") or []:
                if not isinstance(group, dict):
                    continue
                for node in group.get("nodes") or []:
                    if not isinstance(node, dict):
                        continue
                    if str(node.get("primPath") or "").strip() == prim_path:
                        label = str(node.get("labelEn") or node.get("id") or leaf)
                        i18n_key = str(node.get("i18nKey") or "").strip()
                        return {"arrivalLabel": label, "arrivalLabelI18nKey": i18n_key}
        except Exception:
            pass

    for filename in _POI_ARRIVAL_DATA_FILES:
        path = os.path.join(data_dir, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            continue
        rows = raw.get("entries") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            continue
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("xform_id") or "").strip() == leaf:
                label = str(entry.get("display_name") or leaf)
                return {"arrivalLabel": label, "arrivalLabelI18nKey": i18n_key}

    return {"arrivalLabel": label, "arrivalLabelI18nKey": i18n_key}


def register(ctx: NavmeshWireContext, dispatch_view_transition_ready, dispatch_view_transition_ready_after_settle) -> None:
    ext = ctx.ext
    observe = ctx.observe
    normalize_event_payload = ctx.normalize_event_payload
    carb = ctx.carb
    POI_CONFIGS = ctx.poi_configs

    def _on_route_measure_set(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            enabled = payload.get("enabled", True)
            ext._svc.set_route_measure_enabled(bool(enabled))
        except Exception as e:
            print(f"[navmesh_route] routeMeasureSet failed: {e}")

    def _resolve_player_ref_for_poi_lists():
        """Pick the player position to measure POI routes from."""
        try:
            s = carb.settings.get_settings()
            view_type = str(s.get("/younite/camera/viewType") or "firstPerson")
            if view_type == "birdEye" and s.get("/younite/player/lastFpPosValid"):
                return (
                    float(s.get("/younite/player/lastFpPosX") or 0),
                    float(s.get("/younite/player/lastFpPosY") or 0),
                    float(s.get("/younite/player/lastFpPosZ") or 0),
                )
        except Exception:
            pass
        return "/World/PlayerCharacter"

    def _on_routes_to_exits_request(evt):
        """Exit route handler with data-gating."""
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            exit_refs = payload.get("exitRefs") or payload.get("exit_refs") or []
            if not isinstance(exit_refs, (list, tuple)):
                exit_refs = [exit_refs]
            if not exit_refs:
                cfg = POI_CONFIGS["exit"]
                exit_refs = discover_pois(cfg["prefix"], data_lookup=cfg.get("_data_lookup"))
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            use_wp = POI_CONFIGS["exit"].get("use_waypoints", False)
            results = ext._svc.compute_routes_to_exits(list(exit_refs), use_waypoints=use_wp)
            enrich_results(results, POI_CONFIGS["exit"].get("_data_lookup"))
            dispatch_to_events2("navmeshRoutesToExitsResult", {"results": results[: POI_CONFIGS["exit"]["max_results"]]})
        except Exception as e:
            print(f"[navmesh_route] navmeshRoutesToExitsRequest failed: {e}")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("navmeshRoutesToExitsResult", {"results": [], "error": str(e)})
            except Exception:
                pass

    def _on_routes_to_pois_request(evt):
        """Generic POI route handler. Payload: { poiType }"""
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            poi_type = payload.get("poiType") or payload.get("poi_type") or ""
            cfg = POI_CONFIGS.get(poi_type)
            if not cfg:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("navmeshRoutesToPoisResult", {
                    "poiType": poi_type, "results": [], "error": f"Unknown poiType: {poi_type}"
                })
                return
            refs = discover_pois(cfg["prefix"], data_lookup=cfg.get("_data_lookup"))
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            use_wp = cfg.get("use_waypoints", False)
            player_ref = _resolve_player_ref_for_poi_lists()
            data_lookup = cfg.get("_data_lookup")
            stream_list = poi_type in ("restroom", "quiet_zone")
            max_results = cfg["max_results"] if "max_results" in cfg else None

            def _emit_poi_results(chunk: list, done: bool) -> None:
                enrich_results(chunk, data_lookup)
                out = list(chunk)
                if done and max_results is not None:
                    out = out[:max_results]
                dispatch_to_events2("navmeshRoutesToPoisResult", {
                    "poiType": poi_type,
                    "results": out,
                    "partial": not done,
                })

            results = ext._svc.compute_routes_to_exits(
                list(refs),
                player_ref=player_ref,
                use_waypoints=use_wp,
                poi_list_cache_type=poi_type if stream_list else None,
                on_progress=_emit_poi_results if stream_list else None,
            )
            if not stream_list:
                enrich_results(results, data_lookup)
                max_results = cfg["max_results"] if "max_results" in cfg else 10
                capped = results if max_results is None else results[:max_results]
                dispatch_to_events2("navmeshRoutesToPoisResult", {
                    "poiType": poi_type, "results": capped,
                })
        except Exception as e:
            print(f"[navmesh_route] navmeshRoutesToPoisRequest failed: {e}")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("navmeshRoutesToPoisResult", {
                    "poiType": payload.get("poiType", ""), "results": [], "error": str(e)
                })
            except Exception:
                pass

    observe("routeMeasureSet", _on_route_measure_set)
    observe("navmeshRoutesToExitsRequest", _on_routes_to_exits_request)
    observe("navmeshRoutesToPoisRequest", _on_routes_to_pois_request)

    def _on_poi_teleport(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        prim_path = str(payload.get("primPath") or payload.get("prim_path") or "").strip()
        if not prim_path:
            return

        try:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if not stage:
                raise RuntimeError("No USD stage")

            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                raise RuntimeError(f"Prim not found: {prim_path}")

            from younite.usd_viewer_stage_core_extension.teleport_registry import get_teleport_service

            tp = get_teleport_service()
            if not tp:
                raise RuntimeError("TeleportService not available")

            # Match spawn-point facing: nested prims (e.g. NavShortcuts elevator
            # floors) use world forward; direct /World children use authored
            # local rotateXYZ / rotateYXZ via TeleportService.
            spawn_translate, spawn_rotate, _rot_type = tp._read_spawn_point_transform(prim)
            body_yaw_deg = float(spawn_rotate[1])

            ok = tp.teleport_to_coordinates(
                float(spawn_translate[0]),
                float(spawn_translate[1]),
                float(spawn_translate[2]),
                world_body_yaw_deg=body_yaw_deg,
            )
            if not ok:
                raise RuntimeError("teleport_to_coordinates returned False")

            print(
                f"[navmesh_route] POI teleport to {prim_path} at "
                f"({spawn_translate[0]:.1f}, {spawn_translate[1]:.1f}, {spawn_translate[2]:.1f}), "
                f"yaw={body_yaw_deg:.1f}°"
            )
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            arrival = _arrival_label_for_prim_path(prim_path)
            dispatch_to_events2(
                "poiTeleportResult",
                {
                    "primPath": prim_path,
                    "success": True,
                    "arrivalLabel": arrival.get("arrivalLabel") or _prim_leaf(prim_path),
                    "arrivalLabelI18nKey": arrival.get("arrivalLabelI18nKey") or "",
                },
            )
            asyncio.ensure_future(dispatch_view_transition_ready_after_settle(True))
        except Exception as e:
            print(f"[navmesh_route] POI teleport failed: {e}")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("poiTeleportResult", {"primPath": prim_path, "success": False, "error": str(e)})
            except Exception:
                pass
            dispatch_view_transition_ready(False)

    observe("poiTeleport", _on_poi_teleport)
