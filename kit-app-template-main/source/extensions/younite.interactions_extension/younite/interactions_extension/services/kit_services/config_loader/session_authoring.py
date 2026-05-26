"""Session-layer USD authoring: payloads, colliders, NPC spawn Xforms."""
from __future__ import annotations

from typing import Optional, Tuple

from .... import usd_helpers


def attach_payload_and_collider(
    prim_path: str,
    asset_rel_path: str,
    *,
    data_root,
    collider_translate: Tuple[float, float, float],
    collider_scale: Tuple[float, float, float],
    purpose_label: str = "iconGroup",
) -> None:
    """Attach a payload reference + invisible Collider child via session-layer override."""
    try:
        import omni.usd
        from pxr import Sdf, Usd, UsdGeom, UsdPhysics, Gf

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return

        if not data_root:
            return
        abs_asset = (data_root / asset_rel_path).resolve()
        asset_str = str(abs_asset).replace("\\", "/")

        session_layer = stage.GetSessionLayer()

        parent_spec = Sdf.CreatePrimInLayer(session_layer, Sdf.Path(prim_path))
        if parent_spec is None:
            print(
                f"[interactions] {purpose_label}: cannot create primSpec on session layer for {prim_path}"
            )
            return

        existing_assets = {str(item.assetPath) for item in
                           list(parent_spec.payloadList.prependedItems) +
                           list(parent_spec.payloadList.appendedItems)}
        if asset_str not in existing_assets:
            parent_spec.payloadList.prependedItems.append(Sdf.Payload(asset_str))

        collider_path = Sdf.Path(prim_path).AppendChild("Collider")
        collider_existing = stage.GetPrimAtPath(collider_path)
        if collider_existing and collider_existing.IsValid():
            return
        if session_layer.GetPrimAtPath(collider_path) is not None:
            return
        Sdf.PrimSpec(parent_spec, "Collider", Sdf.SpecifierDef, "Cube")

        with Usd.EditContext(stage, session_layer):
            cube_prim = stage.GetPrimAtPath(collider_path)
            if cube_prim and cube_prim.IsValid():
                cube = UsdGeom.Cube(cube_prim)
                cube.AddTranslateOp().Set(
                    Gf.Vec3d(collider_translate[0], collider_translate[1], collider_translate[2])
                )
                cube.AddScaleOp().Set(
                    Gf.Vec3f(collider_scale[0], collider_scale[1], collider_scale[2])
                )
                cube.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                try:
                    collision = UsdPhysics.CollisionAPI.Apply(cube_prim)
                    collision.CreateCollisionEnabledAttr().Set(True)
                except Exception:
                    pass
                try:
                    from pxr import PhysxSchema
                    PhysxSchema.PhysxCollisionAPI.Apply(cube_prim)
                except Exception:
                    pass
    except Exception as ex:
        print(f"[interactions] {purpose_label}: attach_payload_and_collider failed for {prim_path}: {ex}")


def attach_icon_payload(prim_path: str, asset_rel_path: str, *, data_root) -> None:
    """Icon defaults: collider centered ~waist height for the speaker mesh."""
    attach_payload_and_collider(
        prim_path,
        asset_rel_path,
        data_root=data_root,
        collider_translate=(0.0, 30.0, 0.0),
        collider_scale=(20.0, 30.0, 20.0),
    )


def attach_coin_payload(
    prim_path: str,
    asset_rel_path: str,
    *,
    data_root,
    model_rotation_xyz=(0.0, 90.0, 0.0),
    model_scale_xyz=(0.25, 0.25, 0.25),
    spin_axis: str = "z",
    spin_enabled: bool = True,
) -> None:
    """Attach a POI coin asset on a session-layer ``CoinModel`` child xForm.

    Why a child wrapper: the coin asset's "arrow forward" is baked along
    one local axis but the user-authored coin xForm rotation expresses
    *where* they want the arrow to point. The wrapper holds a fixed
    asset-axis correction (``model_rotation_xyz``) so the parent xForm
    stays free for the author and the registry / asset can be swapped
    without re-authoring every coin xForm.

    ``model_scale_xyz`` is applied on ``CoinModel`` (not the anchor xForm)
    so ``coins_layer`` anchors stay translate + rotate only; tune size in
    ``coins_registry.json`` via ``modelScale``. It is authored as a
    suffixed ``xformOp:scale:registry`` op so it **multiplies with**
    rather than overrides any ``xformOp:scale`` baked into the asset's
    defaultPrim — Y-up ``coin_toilet_unisex.usd`` has scale ``1`` while
    every Z-up ``other_coins/*.usdc`` bakes in scale ``100``, so a
    single ``modelScale: 0.25`` keeps both at the same final visual
    size (``0.25 × 1`` and ``0.25 × 100`` respectively).

    When ``spin_enabled`` is true (default), a ``xformOp:rotate*:spin``
    op is authored at ``0`` on ``CoinModel`` and
    ``InteractionMarkerService`` drives it per frame (see
    ``register_coin_spinners``). Set false (or ``spinAxis: none`` in
    ``coins_registry.json`` via ``coins_loader``) for a static coin.

    A standard invisible ``Cube "Collider"`` is added on the **parent**
    coin xForm (not the wrapper) so the existing click-router parent-walk
    keeps matching the registered click prim path. Collider size is
    scaled by ``model_scale_xyz`` so picking stays consistent when the
    anchor no longer carries a scale op.
    """
    try:
        import omni.usd
        from pxr import Sdf, Usd, UsdGeom, UsdPhysics, Gf

        stage = omni.usd.get_context().get_stage()
        if stage is None or not data_root:
            return
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return

        abs_asset = (data_root / asset_rel_path).resolve()
        asset_str = str(abs_asset).replace("\\", "/")

        session_layer = stage.GetSessionLayer()

        parent_spec = Sdf.CreatePrimInLayer(session_layer, Sdf.Path(prim_path))
        if parent_spec is None:
            print(f"[interactions] coin: cannot create primSpec on session layer for {prim_path}")
            return

        model_path = Sdf.Path(prim_path).AppendChild("CoinModel")
        model_spec = session_layer.GetPrimAtPath(model_path)
        if model_spec is None:
            model_spec = Sdf.PrimSpec(parent_spec, "CoinModel", Sdf.SpecifierDef, "Xform")
        else:
            model_spec.specifier = Sdf.SpecifierDef
            if not model_spec.typeName:
                model_spec.typeName = "Xform"

        existing_assets = {
            str(item.assetPath)
            for item in list(model_spec.payloadList.prependedItems)
            + list(model_spec.payloadList.appendedItems)
        }
        if asset_str not in existing_assets:
            model_spec.payloadList.prependedItems.append(Sdf.Payload(asset_str))

        sx = float(model_scale_xyz[0])
        sy = float(model_scale_xyz[1])
        sz = float(model_scale_xyz[2])

        with Usd.EditContext(stage, session_layer):
            model_prim = stage.GetPrimAtPath(model_path)
            if model_prim and model_prim.IsValid():
                xf = UsdGeom.Xformable(model_prim)
                rot_value = Gf.Vec3f(
                    float(model_rotation_xyz[0]),
                    float(model_rotation_xyz[1]),
                    float(model_rotation_xyz[2]),
                )
                # The asset payload contributes its own xformOps onto
                # CoinModel (defaultPrim "World" usually authors
                # translate/rotateXYZ/scale). Author a session-layer
                # opinion on the existing rotateXYZ op when present;
                # otherwise add a fresh op. Either way the session
                # layer wins composition, so the parent xForm rotation
                # remains the per-instance "where the arrow points"
                # knob and this op is just the asset-axis correction.
                existing_rot_op = None
                for op in xf.GetOrderedXformOps():
                    if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
                        existing_rot_op = op
                        break
                if existing_rot_op is not None:
                    existing_rot_op.Set(rot_value)
                else:
                    xf.AddRotateXYZOp().Set(rot_value)

                # Registry scale op. Suffixed (`xformOp:scale:registry`)
                # so it MULTIPLIES with the asset's authored `xformOp:scale`
                # instead of overriding it. Z-up `.usdc` coins bake in
                # scale 100; overriding with 0.25 shrinks them ~400x.
                scale_attr_name = "xformOp:scale:registry"
                scale_op = None
                for op in xf.GetOrderedXformOps():
                    if str(op.GetOpName()) == scale_attr_name:
                        scale_op = op
                        break
                if scale_op is None:
                    scale_op = xf.AddScaleOp(opSuffix="registry")
                scale_op.Set(Gf.Vec3f(sx, sy, sz))

                spin_attr_name: Optional[str] = None
                if spin_enabled:
                    # Per-frame spin op in CoinModel-local space (see
                    # ``InteractionMarkerService`` mode ``coin``). The
                    # ``:spin`` suffix avoids colliding with asset ops.
                    axis = (spin_axis or "z").lower().strip()
                    if axis == "x":
                        spin_attr_name = "xformOp:rotateX:spin"
                    elif axis == "y":
                        spin_attr_name = "xformOp:rotateY:spin"
                    else:
                        spin_attr_name = "xformOp:rotateZ:spin"

                    spin_op = None
                    for op in xf.GetOrderedXformOps():
                        if str(op.GetOpName()) == spin_attr_name:
                            spin_op = op
                            break
                    if spin_op is None:
                        if axis == "x":
                            spin_op = xf.AddRotateXOp(opSuffix="spin")
                        elif axis == "y":
                            spin_op = xf.AddRotateYOp(opSuffix="spin")
                        else:
                            spin_op = xf.AddRotateZOp(opSuffix="spin")
                    spin_op.Set(0.0)

                # Outer transforms first in xformOpOrder (USD: first =
                # outermost). Optional spin, then registry scale, then
                # payload/asset ops.
                order_attr = xf.GetXformOpOrderAttr()
                current_order = list(order_attr.Get() or [])
                if not current_order:
                    current_order = [
                        str(o.GetOpName())
                        for o in xf.GetOrderedXformOps()
                        if o.GetOpType() != UsdGeom.XformOp.TypeInvalid
                    ]
                outer: list[str] = []
                if spin_attr_name:
                    while spin_attr_name in current_order:
                        current_order.remove(spin_attr_name)
                    outer.append(spin_attr_name)
                while scale_attr_name in current_order:
                    current_order.remove(scale_attr_name)
                outer.append(scale_attr_name)
                new_order = outer + current_order
                if new_order:
                    order_attr.Set(new_order)

        collider_path = Sdf.Path(prim_path).AppendChild("Collider")
        collider_existing = stage.GetPrimAtPath(collider_path)
        if collider_existing and collider_existing.IsValid():
            return
        if session_layer.GetPrimAtPath(collider_path) is not None:
            return
        Sdf.PrimSpec(parent_spec, "Collider", Sdf.SpecifierDef, "Cube")

        with Usd.EditContext(stage, session_layer):
            cube_prim = stage.GetPrimAtPath(collider_path)
            if cube_prim and cube_prim.IsValid():
                cube = UsdGeom.Cube(cube_prim)
                cube.AddTranslateOp().Set(Gf.Vec3d(0.0, 30.0 * sy, 0.0))
                cube.AddScaleOp().Set(Gf.Vec3f(20.0 * sx, 30.0 * sy, 20.0 * sz))
                cube.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                try:
                    UsdPhysics.CollisionAPI.Apply(cube_prim).CreateCollisionEnabledAttr().Set(True)
                except Exception:
                    pass
                try:
                    from pxr import PhysxSchema
                    PhysxSchema.PhysxCollisionAPI.Apply(cube_prim)
                except Exception:
                    pass
    except Exception as ex:
        print(f"[interactions] coin: attach_coin_payload failed for {prim_path}: {ex}")


def _apply_navmesh_exclude_on_asset_root(prim_path: str) -> None:
    """Exclude the loaded avatar payload meshes from NavMesh baking."""
    try:
        import omni.usd
        from pxr import Sdf, Usd

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return
        session_layer = stage.GetSessionLayer()
        if session_layer is None:
            return

        asset_root_path = f"{prim_path}/World"
        asset_prim = stage.GetPrimAtPath(asset_root_path)
        if not asset_prim or not asset_prim.IsValid():
            return

        with Usd.EditContext(stage, session_layer):
            spec = session_layer.GetPrimAtPath(Sdf.Path(asset_root_path))
            if spec is None:
                spec = Sdf.CreatePrimInLayer(session_layer, Sdf.Path(asset_root_path))
            if spec is None:
                return
            schemas = list(spec.apiSchemas.prependedItems)
            if "NavMeshExcludeAPI" not in schemas:
                schemas.insert(0, "NavMeshExcludeAPI")
                spec.apiSchemas.prependedItems = schemas
    except Exception as ex:
        print(
            f"[interactions] npc: NavMeshExcludeAPI on asset root failed for {prim_path}: {ex}"
        )


def attach_npc_payload(prim_path: str, npc_cfg: dict, *, data_root) -> None:
    """Session-layer character payload + invisible Collider (humanoid defaults)."""
    asset_rel = str(npc_cfg.get("avatarAsset") or "").strip()
    if not asset_rel:
        return
    tx, ty, tz = 0.0, 90.0, 0.0
    sx, sy, sz = 30.0, 90.0, 20.0
    cc = npc_cfg.get("collider")
    if isinstance(cc, dict):
        tr = cc.get("translate")
        if isinstance(tr, (list, tuple)) and len(tr) >= 3:
            tx, ty, tz = float(tr[0]), float(tr[1]), float(tr[2])
        sc = cc.get("scale")
        if isinstance(sc, (list, tuple)) and len(sc) >= 3:
            sx, sy, sz = float(sc[0]), float(sc[1]), float(sc[2])
    attach_payload_and_collider(
        prim_path,
        asset_rel,
        data_root=data_root,
        collider_translate=(tx, ty, tz),
        collider_scale=(sx, sy, sz),
        purpose_label="npc",
    )
    _apply_navmesh_exclude_on_asset_root(prim_path)
    create_or_update_npc_spawn_point(prim_path, npc_cfg)
    try:
        from ..avatar_nav_exclusion import (
            ensure_avatar_nav_exclusion,
            register_avatar_nav_exclusion,
        )

        register_avatar_nav_exclusion(prim_path)
        # Place volume before bake; Y is refined on navmeshDualBakeComplete + one rebake.
        ensure_avatar_nav_exclusion(prim_path, request_rebake=False)
    except Exception as ex:
        print(f"[interactions] npc: avatar nav exclusion skipped for {prim_path}: {ex}")


def create_or_update_npc_spawn_point(avatar_prim_path: str, npc_cfg: dict) -> None:
    """Session-layer ``<avatar>/PlayerSpawnPoint_*`` — child of the NPC."""
    if npc_cfg.get("skipNpcSpawn"):
        return
    try:
        import re

        import omni.usd
        from pxr import Gf, Sdf, Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return
        avatar_prim = stage.GetPrimAtPath(avatar_prim_path)
        if not avatar_prim or not avatar_prim.IsValid():
            return

        name_hint = str(npc_cfg.get("spawnPointPrimName") or "").strip()
        if name_hint:
            spawn_leaf = name_hint.split("/")[-1].strip()
            if not spawn_leaf.startswith("PlayerSpawnPoint_"):
                spawn_leaf = f"PlayerSpawnPoint_{spawn_leaf}"
        else:
            raw = str(npc_cfg.get("avatarName") or "NPC").strip()
            suffix = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_") or "NPC"
            spawn_leaf = f"PlayerSpawnPoint_{suffix}"

        mpu = float(usd_helpers.get_stage_meters_per_unit(stage) or 0.01)
        if mpu <= 0.0:
            mpu = 0.01
        dist_m = float(npc_cfg.get("npcSpawnMeters", 1.0) or 1.0)
        step = dist_m / mpu

        z_sign = float(npc_cfg.get("npcSpawnForwardLocalZ", 1.0) or 1.0)
        if z_sign not in (-1.0, 1.0):
            z_sign = 1.0

        session_layer = stage.GetSessionLayer()

        legacy_path = f"/World/{spawn_leaf}"
        try:
            legacy_spec = session_layer.GetPrimAtPath(Sdf.Path(legacy_path))
            if legacy_spec is not None:
                session_layer.RemovePrim(legacy_spec)
        except Exception:
            pass

        parent_path = str(avatar_prim_path).rstrip("/")
        nested_path = f"{parent_path}/{spawn_leaf}"

        parent_spec = Sdf.CreatePrimInLayer(session_layer, Sdf.Path(parent_path))
        if parent_spec is None:
            return
        spawn_spec = session_layer.GetPrimAtPath(Sdf.Path(nested_path))
        if spawn_spec is None:
            spawn_spec = Sdf.PrimSpec(parent_spec, spawn_leaf, Sdf.SpecifierDef, "Xform")
        else:
            spawn_spec.specifier = Sdf.SpecifierDef
            if not spawn_spec.typeName:
                spawn_spec.typeName = "Xform"

        with Usd.EditContext(stage, session_layer):
            sp = stage.GetPrimAtPath(nested_path)
            if not sp or not sp.IsValid():
                return
            xf = UsdGeom.Xformable(sp)
            xf.ClearXformOpOrder()
            xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(
                Gf.Vec3d(0.0, 0.0, z_sign * step)
            )
    except Exception as ex:
        print(f"[interactions] npc spawn point failed for {avatar_prim_path}: {ex}")
