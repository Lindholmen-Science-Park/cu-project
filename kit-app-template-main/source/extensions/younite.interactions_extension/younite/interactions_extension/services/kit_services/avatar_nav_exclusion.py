"""NavMesh exclusion under NPC avatars — one rectangular Exclude volume (POI / 360° pattern).

Uses a single ``NavMeshVolume`` + ``nav:volume:type = "Exclude"`` on ``navigation_layer.usda``,
matching ``NavMeshVolume_01`` etc. Scale matches POI volumes ``(2, 2, 2)`` footprint — not a thin
slice (thin Y caused jagged overlay edges). Legacy ring/disc prims are purged before authoring.
"""
from __future__ import annotations

from typing import Optional, Set, Tuple

_NAV_LAYER_FILENAME = "navigation_layer.usda"
EXCLUSIONS_PARENT_PATH = "/World/AvatarNavExclusions"
VOLUME_HALF_EXTENT_CM = 50.0
# ~75 cm radius → 1.5 m square; default npcSpawnMeters (1 m) stays outside the carved hole.
DEFAULT_RADIUS_CM = 75.0
GROUND_OFFSET_CM = 0.5
# POI holes use (2, 2, 2) on the ±50 cm box → 200 cm cube. Thin Y (0.12) carved a ragged slice.
POI_VOLUME_Y_SCALE = 2.0

_pending_avatar_paths: Set[str] = set()
_post_snap_rebake_done = False


def register_avatar_nav_exclusion(avatar_prim_path: str) -> None:
    path = str(avatar_prim_path or "").strip()
    if path:
        _pending_avatar_paths.add(path)
        ensure_avatar_nav_exclusion(path, request_rebake=False)


def _find_nav_layer(stage):
    from pxr import Sdf

    root_layer = stage.GetRootLayer()
    for sub_path in root_layer.subLayerPaths:
        if _NAV_LAYER_FILENAME in sub_path:
            layer = Sdf.Layer.FindRelativeToLayer(root_layer, sub_path)
            if layer:
                return layer
    return None


def _exclude_volume_scale(radius_cm: float) -> Tuple[float, float, float]:
    r = max(float(radius_cm), 60.0)
    diameter = r * 2.0
    xz = diameter / (VOLUME_HALF_EXTENT_CM * 2.0)
    return xz, POI_VOLUME_Y_SCALE, xz


def _snap_y_to_navmesh(wx: float, y_hint: float, wz: float) -> float:
    try:
        import carb
        from younite.navmesh_route_extension.navmesh_route_bridge import (
            get_navmesh_mode_cache_for_dev,
        )

        cache = get_navmesh_mode_cache_for_dev()
        nm = cache.get_active_navmesh() if cache else None
        if nm is None:
            return float(y_hint)
        result = nm.query_closest_point(target=carb.Float3(float(wx), float(y_hint), float(wz)))
        if result is None:
            return float(y_hint)
        cp, _ = result
        if cp is None:
            return float(y_hint)
        return float(cp.y) + GROUND_OFFSET_CM
    except Exception as ex:
        print(f"[interactions] avatar nav exclusion: navmesh snap failed: {ex}")
        return float(y_hint)


def _avatar_world_anchor(stage, avatar_prim_path: str) -> Optional[Tuple[float, float, float]]:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(avatar_prim_path)
    if not prim or not prim.IsValid():
        return None

    xf = UsdGeom.Xformable(prim)
    world_xf = xf.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    t = world_xf.ExtractTranslation()
    wx, wy, wz = float(t[0]), float(t[1]), float(t[2])
    wy = _snap_y_to_navmesh(wx, wy, wz)
    return wx, wy, wz


def _author_exclude_volume(stage, path: str, *, scale: Tuple[float, float, float]) -> None:
    from pxr import Gf, Sdf, UsdGeom

    half = VOLUME_HALF_EXTENT_CM
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        prim = stage.DefinePrim(path, "NavMeshVolume")

    prim.SetMetadata("apiSchemas", Sdf.TokenListOp.Create({"NavMeshAreaAPI"}))
    gprim = UsdGeom.Gprim(prim)
    gprim.CreateExtentAttr().Set(
        [
            Gf.Vec3f(-half, -half, -half),
            Gf.Vec3f(half, half, half),
        ]
    )
    xf = UsdGeom.Xformable(prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.0, 0.0, 0.0))
    xf.AddScaleOp().Set(Gf.Vec3f(scale[0], scale[1], scale[2]))

    prim.CreateAttribute("nav:area", Sdf.ValueTypeNames.String).Set("Walkable")
    prim.CreateAttribute("nav:volume:type", Sdf.ValueTypeNames.Token).Set("Exclude")


def _purge_avatar_exclusion_root(stage, root_path: str) -> None:
    """Remove an avatar exclusion subtree (drops ring/disc experiments from prior bakes)."""
    prim = stage.GetPrimAtPath(root_path)
    if prim and prim.IsValid():
        stage.RemovePrim(root_path)


def ensure_avatar_nav_exclusion(
    avatar_prim_path: str,
    *,
    radius_cm: float = DEFAULT_RADIUS_CM,
    request_rebake: bool = False,
) -> Optional[str]:
    try:
        import omni.usd
        from pxr import Gf, Sdf, Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if not stage:
            print("[interactions] avatar nav exclusion: no stage")
            return None

        anchor = _avatar_world_anchor(stage, avatar_prim_path)
        if anchor is None:
            print(
                f"[interactions] avatar nav exclusion: avatar prim missing {avatar_prim_path}"
            )
            return None

        wx, wy, wz = anchor
        leaf = avatar_prim_path.rstrip("/").split("/")[-1] or "Avatar"
        root_path = f"{EXCLUSIONS_PARENT_PATH}/{leaf}"
        volume_path = f"{root_path}/ExcludeVolume"

        nav_layer = _find_nav_layer(stage)
        if not nav_layer:
            print("[interactions] avatar nav exclusion: navigation sublayer not found")
            nav_layer = stage.GetRootLayer()

        vol_scale = _exclude_volume_scale(radius_cm)

        with Usd.EditContext(stage, nav_layer):
            parent = stage.GetPrimAtPath(EXCLUSIONS_PARENT_PATH)
            if not parent or not parent.IsValid():
                stage.DefinePrim(EXCLUSIONS_PARENT_PATH, "Xform")

            # Full replace — guarantees no stale ExcludeRing_* / ExcludeFill_* on the nav layer.
            _purge_avatar_exclusion_root(stage, root_path)

            stage.DefinePrim(root_path, "Xform")
            root_xf = UsdGeom.Xformable(stage.GetPrimAtPath(root_path))
            root_xf.ClearXformOpOrder()
            root_xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                Gf.Vec3d(wx, wy, wz)
            )
            _author_exclude_volume(stage, volume_path, scale=vol_scale)

        try:
            from younite.payload_orchestrator_core_extension import Priority, show

            show(EXCLUSIONS_PARENT_PATH, Priority.HIGH, source="avatar_nav_exclusion")
            show(root_path, Priority.HIGH, source="avatar_nav_exclusion")
            show(volume_path, Priority.HIGH, source="avatar_nav_exclusion")
        except Exception as ex:
            print(f"[interactions] avatar nav exclusion: show() failed: {ex}")

        sx, sy, sz = vol_scale
        print(
            f"[interactions] Avatar nav exclusion '{root_path}' "
            f"world=({wx:.1f}, {wy:.1f}, {wz:.1f}) radius={radius_cm:.0f}cm "
            f"shape=exclude_volume scale=({sx:.2f},{sy:.2f},{sz:.2f}) type=Exclude "
            f"(single box, POI-style)"
        )

        if request_rebake:
            try:
                from younite.navmesh_route_extension.navmesh_route_bridge import (
                    schedule_navmesh_rebake_if_idle,
                )

                schedule_navmesh_rebake_if_idle()
            except Exception:
                from younite.messaging_core_extension.message_utils import dispatch_to_events2

                dispatch_to_events2("navmeshRebakeRequest", {})

        return root_path
    except Exception as ex:
        print(f"[interactions] avatar nav exclusion failed for {avatar_prim_path}: {ex}")
        import traceback

        traceback.print_exc()
        return None


def refresh_pending_avatar_exclusions_after_bake(*, request_rebake: bool = True) -> None:
    global _post_snap_rebake_done

    if not _pending_avatar_paths:
        return

    try:
        import omni.usd

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        any_placed = False
        for path in list(_pending_avatar_paths):
            if ensure_avatar_nav_exclusion(path, request_rebake=False):
                any_placed = True

        if any_placed and request_rebake and not _post_snap_rebake_done:
            _post_snap_rebake_done = True
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            print(
                "[interactions] Avatar nav exclusions snapped — requesting one rebake "
                "so single Exclude volume carves a clean box"
            )
            dispatch_to_events2("navmeshRebakeRequest", {})
    except Exception as ex:
        print(f"[interactions] refresh_pending_avatar_exclusions_after_bake failed: {ex}")


def subscribe_avatar_nav_exclusion_events(subs: list) -> None:
    try:
        import carb.eventdispatcher
        import omni.kit.app as kit_app

        ed = carb.eventdispatcher.get_eventdispatcher()

        def _on_dual_bake(evt):
            payload = getattr(evt, "payload", None) or {}
            if isinstance(payload, dict) and not payload.get("success", True):
                return
            refresh_pending_avatar_exclusions_after_bake(request_rebake=True)

        try:
            kit_app.register_event_alias(
                carb.events.type_from_string("navmeshDualBakeComplete"),
                "navmeshDualBakeComplete",
            )
        except Exception:
            pass

        subs.append(
            ed.observe_event(
                observer_name="younite.interactions_extension/avatarNavExclusionBake",
                event_name="navmeshDualBakeComplete",
                on_event=_on_dual_bake,
                order=50,
            )
        )
    except Exception as ex:
        print(f"[interactions] avatar nav exclusion event subscribe failed: {ex}")
