"""Small parsing / waypoint helpers shared by event handlers."""

from __future__ import annotations


def parse_vec3(payload: dict, keys: list[str]):
    for k in keys:
        if k not in payload:
            continue
        v = payload.get(k)
        if isinstance(v, (list, tuple)) and len(v) >= 3:
            try:
                return (float(v[0]), float(v[1]), float(v[2]))
            except Exception:
                continue
        if isinstance(v, dict):
            x = v.get("x", v.get("X"))
            y = v.get("y", v.get("Y"))
            z = v.get("z", v.get("Z"))
            if x is not None and y is not None and z is not None:
                try:
                    return (float(x), float(y), float(z))
                except Exception:
                    continue
    return None


def compute_poi_waypoints(start_ref, end_ref):
    """Compute corridor waypoints for a POI route. Returns list or None."""
    try:
        import omni.usd

        from ..services.kit_services import waypoint_router
        from ..scripts.navmesh_shortest_path import resolve_position

        ctx = omni.usd.get_context()
        stage = ctx.get_stage() if ctx else None
        if not stage:
            return []
        ref = start_ref if isinstance(start_ref, str) else "/World/PlayerCharacter"
        player_gf = resolve_position(stage, ref, use_ground=True)
        player_t = (float(player_gf[0]), float(player_gf[1]), float(player_gf[2]))
        if isinstance(end_ref, str):
            end_gf = resolve_position(stage, end_ref, use_ground=False)
            target_t = (float(end_gf[0]), float(end_gf[1]), float(end_gf[2]))
        else:
            target_t = (float(end_ref[0]), float(end_ref[1]), float(end_ref[2]))
        return waypoint_router.plan_route_to_position(player_t, target_t)
    except Exception as e:
        print(f"[navmesh_route] POI waypoint routing failed, using direct path: {e}")
        return []
