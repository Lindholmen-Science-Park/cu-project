"""WGS84 geo teleport and dev shortcut toggles."""

from __future__ import annotations

import asyncio

from .wiring import NavmeshWireContext


def register(ctx: NavmeshWireContext, dispatch_view_transition_ready, dispatch_view_transition_ready_after_settle) -> None:
    ext = ctx.ext
    observe = ctx.observe
    normalize_event_payload = ctx.normalize_event_payload

    def _on_geo_teleport(evt):
        payload = normalize_event_payload(getattr(evt, "payload", None) or {})
        try:
            lat = float(payload.get("latitude") if payload.get("latitude") is not None else payload.get("lat") or 0.0)
            lon = float(payload.get("longitude") if payload.get("longitude") is not None else payload.get("lon") or 0.0)
        except (TypeError, ValueError):
            lat, lon = 0.0, 0.0
        try:
            height = float(payload.get("height") if payload.get("height") is not None else payload.get("altitude") or 0.0)
        except (TypeError, ValueError):
            height = 0.0

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            print(f"[navmesh_route] geoTeleport rejected: invalid lat/lon ({lat}, {lon})")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2(
                    "geoTeleportResult",
                    {"success": False, "latitude": lat, "longitude": lon, "error": "invalid_lat_lon"},
                )
            except Exception:
                pass
            dispatch_view_transition_ready(False)
            return

        try:
            from younite.usd_viewer_stage_core_extension import latlon_to_scene_xyz_for_teleport
            from younite.usd_viewer_stage_core_extension.teleport_registry import get_teleport_service

            x, y, z = latlon_to_scene_xyz_for_teleport(lat, lon, height)
            tp = get_teleport_service()
            if not tp:
                raise RuntimeError("TeleportService not available")

            ok = tp.teleport_to_coordinates(float(x), float(y), float(z))
            if not ok:
                raise RuntimeError("teleport_to_coordinates returned False")

            print(
                f"[navmesh_route] geoTeleport applied TeleportService.teleport_to_coordinates "
                f"(scene cm): lat/lon=({lat:.6f},{lon:.6f}) h_m={height} → xyz=({x:.2f},{y:.2f},{z:.2f})"
            )
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2(
                "geoTeleportResult",
                {
                    "success": True,
                    "latitude": lat,
                    "longitude": lon,
                    "height": height,
                    "position": [float(x), float(y), float(z)],
                },
            )
            asyncio.ensure_future(dispatch_view_transition_ready_after_settle(True))
        except Exception as e:
            print(f"[navmesh_route] geoTeleport failed: {e}")
            try:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2(
                    "geoTeleportResult",
                    {"success": False, "latitude": lat, "longitude": lon, "error": str(e)},
                )
            except Exception:
                pass
            dispatch_view_transition_ready(False)

    observe("geoTeleport", _on_geo_teleport)

    def _on_shortcuts_toggle(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            active = bool(payload.get("active", False))
            if ext._shortcut_router is not None:
                if active:
                    try:
                        ext._shortcut_router.reload()
                    except Exception:
                        pass
                ext._shortcut_router.set_enabled(active)
                if active:
                    try:
                        groups = ext._shortcut_router.get_groups()
                        node_count = sum(len(g.nodes) for g in groups)
                        print(
                            f"[navmesh_route] shortcuts ENABLED "
                            f"({len(groups)} groups, {node_count} nodes)"
                        )
                        for g in groups:
                            for n in g.nodes:
                                print(
                                    f"[navmesh_route]   {g.group_id}/{n.node_id} "
                                    f"@ ({n.pos[0]:.1f}, {n.pos[1]:.1f}, {n.pos[2]:.1f})"
                                )
                    except Exception:
                        pass
                else:
                    print("[navmesh_route] shortcuts DISABLED")
            ext._svc.set_shortcuts_active(active)
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2 as _d2e,
            )

            _d2e("shortcutsStatus", {"active": active})
        except Exception as e:
            print(f"[navmesh_route] shortcutsToggle failed: {e}")

    observe("shortcutsToggle", _on_shortcuts_toggle)

    def _on_shortcuts_prefer_toggle(evt):
        try:
            payload = normalize_event_payload(getattr(evt, "payload", None) or {})
            active = bool(payload.get("active", False))
            ext._svc.set_prefer_shortcuts(active)
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2 as _d2e,
            )

            _d2e("shortcutsPreferStatus", {"active": active})
        except Exception as e:
            print(f"[navmesh_route] shortcutsPreferToggle failed: {e}")

    observe("shortcutsPreferToggle", _on_shortcuts_prefer_toggle)
