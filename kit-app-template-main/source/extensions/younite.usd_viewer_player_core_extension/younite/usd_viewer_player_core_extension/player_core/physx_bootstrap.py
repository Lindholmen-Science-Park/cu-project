from __future__ import annotations

import asyncio
import os
from typing import Any

import omni.kit.app as kit_app


class PhysxBootstrap:
    """
    Player bootstrapping + on-demand PhysX CCT management.

    Phase 1 (startup): setup_player_character()
        Lightweight: creates PlayerCharacter, binds camera, places at spawn.
        No PhysX CCT involvement.

    Phase 2 (on-demand): activate_cct()
        Heavy: enables omni.physx.cct, activates CCT, gravity, CharacterController.
        Only called when user selects WASD/joystick mode.

    Phase 3 (on-demand): deactivate_cct()
        Tears down CCT so sweep queries stop.
        Called when user switches back to point-and-click.
    """

    _FIRST_PERSON_SPAWNPOINT = "PlayerSpawnPoint_01"

    def __init__(self, host: Any):
        self._h = host

    # ------------------------------------------------------------------
    # Phase 1: Lightweight player setup (no CCT)
    # ------------------------------------------------------------------

    def setup_player_character(self):
        """
        Create PlayerCharacter at spawn point and bind the viewport camera.
        Does NOT activate PhysX CCT -- purely USD + viewport.
        """
        h = self._h
        try:
            from younite.usd_viewer_stage_core_extension.services.core_services.world_conventions import (
                PLAYER_CHARACTER_PATH,
                find_spawn_point_prim,
                get_valid_prim,
                get_default_view_type,
                default_spawnpoint_for_view,
            )

            player_path = PLAYER_CHARACTER_PATH
            initial_spawnpoint = default_spawnpoint_for_view(get_default_view_type())

            import omni.usd as _omni_usd

            stage = _omni_usd.get_context().get_stage()
            if not stage:
                print("[player_core] No stage available for player init")
                return

            try:
                world = stage.GetPrimAtPath("/World")
                if not (world and world.IsValid()):
                    stage.DefinePrim("/World", "Xform")
            except Exception:
                pass

            spawn_point_prim, spawn_point_path = find_spawn_point_prim(stage, initial_spawnpoint)

            existing_player = get_valid_prim(stage, player_path)

            if not (existing_player and existing_player.IsValid()):
                if not (spawn_point_prim and spawn_point_path):
                    print("[player_core] No spawn point found; cannot spawn PlayerCharacter")
                    return

                created_path = self.create_player_character_from_reference(spawn_point_prim, spawn_point_path)
                if not created_path:
                    print("[player_core] Failed to create PlayerCharacter from reference")
                    return
                player_path = str(created_path)
            else:
                h._player_character_path = player_path

            # Bind viewport to the first-person camera
            self._bind_viewport_camera(player_path)

            h._player_initialized = True

            # Deferred init: re-apply spawn transform + ground snap after
            # the viewport has settled.  Mirrors TeleportService._apply_transform_to_player
            # to produce the correct initial facing direction.
            try:
                h._track_task(asyncio.ensure_future(
                    self._deferred_player_init(player_path, spawn_point_prim, frames_wait=10)
                ))
            except Exception as e:
                print(f"[player_core] Could not schedule deferred init: {e}")

            print("[player_core] Player character setup complete (lightweight, no CCT)")

        except Exception as e:
            print(f"Error setting up player character: {e}")
            import traceback
            traceback.print_exc()

    def _bind_viewport_camera(self, player_path: str):
        """Bind the viewport to the player's first-person camera and hide the capsule mesh."""
        h = self._h
        cam_path = f"{player_path}/first_person_camera"
        try:
            import omni.kit.viewport.utility as vp_utils
            from pxr import UsdGeom, Gf
            import omni.usd as _omni_usd

            stage = _omni_usd.get_context().get_stage()

            # Hide the capsule mesh — without CCT's enable_first_person()
            # the camera would be inside a visible Capsule prim.
            if stage:
                player_prim = stage.GetPrimAtPath(player_path)
                if player_prim and player_prim.IsValid():
                    UsdGeom.Imageable(player_prim).MakeInvisible()

            # Verify camera prim exists; schedule a retry if not resolved yet.
            if stage:
                camera_prim = stage.GetPrimAtPath(cam_path)
                if not camera_prim or not camera_prim.IsValid():
                    h._track_task(asyncio.ensure_future(
                        self.retry_bind_viewport_camera(cam_path, max_frames=180)
                    ))

            vp = vp_utils.get_active_viewport()
            if vp:
                # Switch viewport to the first-person camera
                try:
                    vp.set_active_camera(cam_path)
                except Exception:
                    try:
                        vp.camera_path = cam_path
                    except Exception as e:
                        print(f"[player_core] Failed to set viewport camera: {e}")

                try:
                    vp.update()
                except Exception:
                    pass

                # Wire the movement controller to this camera path
                h._camera_path = cam_path
                try:
                    mc = getattr(h, "_movement_controller", None)
                    if mc:
                        shim = type("PlayerControllerShim", (), {
                            "camera_path": cam_path,
                            "jump": lambda _s: h.jump() if hasattr(h, "jump") else False,
                        })()
                        mc.set_player_controller(shim)
                except Exception:
                    pass

                # Zero out camera rotation (deferred init will apply the final
                # spawn-point rotation after the viewport settles).
                try:
                    cam_prim = stage.GetPrimAtPath(cam_path) if stage else None
                    if cam_prim and cam_prim.IsValid():
                        cam_xf = UsdGeom.Xformable(cam_prim)
                        rot_op = cam_xf.GetRotateXYZOp() or cam_xf.GetRotateYXZOp()
                        if rot_op:
                            rot_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))
                except Exception:
                    pass

                # Disable the viewport's built-in camera controller so it
                # doesn't override our PlayerInputController's rotation.
                try:
                    if hasattr(vp, "set_keyboard_input_enabled"):
                        vp.set_keyboard_input_enabled(False)
                    if hasattr(vp, "set_mouse_input_enabled"):
                        vp.set_mouse_input_enabled(False)
                except Exception:
                    pass

            print(f"[player_core] Viewport bound to {cam_path}")
        except Exception as e:
            print(f"[player_core] Could not set viewport camera: {e}")

    # ------------------------------------------------------------------
    # Phase 2: On-demand CCT activation (WASD/joystick mode)
    # ------------------------------------------------------------------

    def activate_cct(self):
        """
        Activate PhysX CCT for WASD/joystick movement.
        Only called when user switches to WASD mode.
        Assumes setup_player_character() has already run.
        """
        h = self._h
        if getattr(h, "_physx_initialized", False):
            print("[player_core] CCT already active, skipping activation")
            return True

        player_path = getattr(h, "_player_character_path", None) or "/World/PlayerCharacter"
        print(f"[player_core] Activating PhysX CCT for WASD mode at {player_path}...")

        h._camera_view_type = "firstPerson"
        try:
            import carb.settings as _carb_settings
            _carb_settings.get_settings().set("/younite/camera/viewType", "firstPerson")
        except Exception:
            pass

        # Make capsule visible again for CCT (enable_first_person handles the camera)
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom
            stage = _omni_usd.get_context().get_stage()
            if stage:
                player_prim = stage.GetPrimAtPath(player_path)
                if player_prim and player_prim.IsValid():
                    UsdGeom.Imageable(player_prim).MakeVisible()
        except Exception:
            pass

        if not self._try_setup_cct(player_path):
            print("⚠️ CCT activation failed")
            return False

        # Teleport AFTER CCT is active so the CCT physics capsule moves too.
        # USD-only transforms are overridden by the CCT's cached position.
        self._teleport_to_first_person_spawn(player_path)

        h._physx_initialized = True
        h._nvidia_controls_active = True

        print("[player_core] PhysX CCT activated for WASD mode")
        return True

    def _teleport_to_first_person_spawn(self, player_path: str):
        """Move the player prim AND the CCT physics capsule to PlayerSpawnPoint_01."""
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom, Gf
            from younite.usd_viewer_stage_core_extension.services.core_services.world_conventions import (
                find_spawn_point_prim,
            )

            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return

            spawn_prim, _ = find_spawn_point_prim(stage, self._FIRST_PERSON_SPAWNPOINT)
            if not spawn_prim or not spawn_prim.IsValid():
                print(f"[player_core] Spawn point {self._FIRST_PERSON_SPAWNPOINT} not found")
                return

            sp_xf = UsdGeom.Xformable(spawn_prim)
            sp_tr = sp_xf.GetTranslateOp()
            if not sp_tr:
                return
            target_pos = sp_tr.Get()

            sp_rot = Gf.Vec3d(0, 0, 0)
            rot_type = "rotateXYZ"
            rot_op = sp_xf.GetRotateXYZOp()
            if rot_op:
                sp_rot = rot_op.Get()
            else:
                rot_op = sp_xf.GetRotateYXZOp()
                if rot_op:
                    sp_rot = rot_op.Get()
                    rot_type = "rotateYXZ"

            player_prim = stage.GetPrimAtPath(player_path)
            if not player_prim or not player_prim.IsValid():
                return

            # Set USD transform
            px = UsdGeom.Xformable(player_prim)
            t_op = px.GetTranslateOp() or px.AddTranslateOp()
            t_op.Set(target_pos)

            if rot_type == "rotateYXZ":
                r_op = px.GetRotateYXZOp() or px.AddRotateYXZOp()
            else:
                r_op = px.GetRotateXYZOp() or px.AddRotateXYZOp()
            r_op.Set(sp_rot)

            s_op = px.GetScaleOp() or px.AddScaleOp()
            s_op.Set(Gf.Vec3d(1, 1, 1))
            px.SetXformOpOrder([t_op, r_op, s_op])

            # Move the CCT physics capsule to match.
            # set_position expects (str, carb.Double3), not three separate floats.
            cct = getattr(self._h, "_nv_cct_interface", None)
            if cct:
                try:
                    import carb
                    pos = carb.Double3(target_pos[0], target_pos[1], target_pos[2])
                    if hasattr(cct, "set_position"):
                        cct.set_position(player_path, pos)
                    elif hasattr(cct, "teleport"):
                        cct.teleport(player_path, pos)
                except Exception as e:
                    print(f"[player_core] CCT teleport call failed: {e}")

            cam_path = f"{player_path}/first_person_camera"
            cam_prim = stage.GetPrimAtPath(cam_path)
            if cam_prim and cam_prim.IsValid():
                cam_xf = UsdGeom.Xformable(cam_prim)
                cam_rot = cam_xf.GetRotateXYZOp() or cam_xf.AddRotateXYZOp()
                cam_rot.Set(Gf.Vec3d(0, 0, 0))

            mc = getattr(self._h, "_movement_controller", None)
            if mc and hasattr(mc, "reset_rotation_state"):
                mc.reset_rotation_state()

            print(f"[player_core] Teleported to {self._FIRST_PERSON_SPAWNPOINT} "
                  f"({target_pos[0]:.1f}, {target_pos[1]:.1f}, {target_pos[2]:.1f})")
        except Exception as e:
            print(f"[player_core] Teleport to spawn failed: {e}")

    def _try_setup_cct(self, cct_path: str) -> bool:
        """
        Core CCT setup: activate CCT, gravity, sync position,
        and wire CharacterController input bindings.
        Camera is already bound by setup_player_character().
        omni.physx.cct must be loaded at startup via the .kit file.
        """
        h = self._h
        try:
            try:
                from omni.physxcct.scripts import utils as nv_utils
            except ImportError as e:
                print(f"[player_core] omni.physxcct not available: {e}")
                return False

            cct = nv_utils.get_physx_cct_interface()
            if not cct:
                print("[player_core] CCT interface is None")
                return False

            cam_path = getattr(h, "_camera_path", None) or f"{cct_path}/first_person_camera"

            def _call(method_name, *args):
                """Call a CCT method, trying snake_case, camelCase, and PascalCase."""
                for m in (method_name,
                          method_name.replace("_", ""),
                          "".join(p.capitalize() for p in method_name.split("_"))):
                    if hasattr(cct, m):
                        return getattr(cct, m)(*args)
                raise AttributeError(f"CCT has no method like '{method_name}'")

            # Activate CCT (required)
            try:
                _call("activate_cct", cct_path)
            except Exception as e:
                print(f"[player_core] Failed to activate CCT: {e}")
                return False

            # Optional CCT configuration (non-fatal)
            for method, args in [
                ("enable_first_person", (cct_path, cam_path)),
                ("enable_worldspace_move", (cct_path, False)),
            ]:
                try:
                    _call(method, *args)
                except Exception:
                    pass

            # Enable gravity (try primary method, then fallback)
            gravity_ok = False
            try:
                _call("enable_gravity", cct_path)
                gravity_ok = True
            except Exception:
                try:
                    if hasattr(cct, "set_gravity_enabled"):
                        cct.set_gravity_enabled(cct_path, True)
                        gravity_ok = True
                except Exception:
                    pass
            if not gravity_ok:
                print("[player_core] Could not enable gravity for CCT")

            h._nv_cct_interface = cct
            h._player_character_path = cct_path

            # Wire CharacterController + input bindings
            self._setup_character_controller_inputs(nv_utils, cct_path)

            return True

        except Exception as e:
            print(f"[player_core] CCT setup error: {e}")
            return False

    def _setup_character_controller_inputs(self, nv_utils, cct_path: str):
        """Create CharacterController, register inputs, and stage-update node."""
        h = self._h
        try:
            im = getattr(nv_utils, "get_input_manager", None)
            if not callable(im):
                return
            input_mgr = im()
            if not input_mgr:
                return

            CC = getattr(nv_utils, "CharacterController", None)
            controller = CC(cct_path) if CC else None
            if controller:
                h._nv_character_controller = controller
                if hasattr(controller, "setup_controls"):
                    try:
                        from .speed_tuner import BASE_CCT_SPEED
                        initial_speed = BASE_CCT_SPEED * float(getattr(h, "_movement_speed_multiplier", 1.0))
                        controller.setup_controls(initial_speed)
                    except Exception:
                        pass

            # Register input bindings (try controller first, then input manager)
            bound = False
            if controller:
                for attr in ("register_inputs", "registerInputs", "bind_inputs"):
                    if hasattr(controller, attr):
                        try:
                            getattr(controller, attr)()
                            bound = True
                            break
                        except Exception:
                            pass
            if not bound and hasattr(input_mgr, "register_default_bindings"):
                try:
                    input_mgr.register_default_bindings()
                    bound = True
                except Exception:
                    pass

            h._nvidia_input_bound = bound

            # Register stage-update node
            reg = getattr(nv_utils, "register_stage_update_node", None)
            if callable(reg):
                try:
                    reg("CCT Controls")
                except TypeError:
                    try:
                        reg()
                    except Exception:
                        pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Phase 3: On-demand CCT deactivation (back to point-and-click)
    # ------------------------------------------------------------------

    def deactivate_cct(self):
        """
        Deactivate PhysX CCT to stop sweep queries.
        Called when user switches back to point-and-click mode.
        """
        h = self._h
        if not getattr(h, "_physx_initialized", False):
            return

        player_path = getattr(h, "_player_character_path", None) or "/World/PlayerCharacter"

        cct = getattr(h, "_nv_cct_interface", None)
        if cct:
            for method in ("deactivate_cct", "deactivateCct", "DeactivateCct"):
                if hasattr(cct, method):
                    try:
                        getattr(cct, method)(player_path)
                        break
                    except Exception:
                        pass
            for method in ("disable_gravity", "disableGravity", "DisableGravity"):
                if hasattr(cct, method):
                    try:
                        getattr(cct, method)(player_path)
                        break
                    except Exception:
                        pass

        # Clear CCT state
        h._nv_cct_interface = None
        h._nv_character_controller = None
        h._physx_initialized = False
        h._nvidia_controls_active = False
        h._nvidia_input_bound = False

        # Hide capsule mesh again (camera would be inside it without CCT)
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom
            stage = _omni_usd.get_context().get_stage()
            if stage:
                player_prim = stage.GetPrimAtPath(player_path)
                if player_prim and player_prim.IsValid():
                    UsdGeom.Imageable(player_prim).MakeInvisible()
        except Exception:
            pass

        print(f"[player_core] CCT deactivated at {player_path}")

    # ------------------------------------------------------------------
    # Deferred player init (mirrors TeleportService._apply_transform_to_player)
    # ------------------------------------------------------------------

    async def _deferred_player_init(self, player_path: str, spawn_point_prim, frames_wait: int = 10):
        """
        Re-apply the spawn-point transform and reset the camera a few frames
        after player setup, once the viewport / physics have settled.

        This mirrors TeleportService._apply_transform_to_player exactly —
        the same code path that produces the correct facing direction when
        returning from bird's-eye view.
        """
        h = self._h
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom, Gf

            app = kit_app.get_app()
            for _ in range(int(frames_wait)):
                await app.next_update_async()

            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return

            player_prim = stage.GetPrimAtPath(player_path)
            if not player_prim or not player_prim.IsValid():
                return

            # --- Read spawn point transform (same logic as TeleportService) ---
            spawn_translate = Gf.Vec3d(0, 0, 0)
            spawn_rotate = Gf.Vec3d(0, 0, 0)
            spawn_rotate_type = "rotateXYZ"

            if spawn_point_prim and spawn_point_prim.IsValid():
                sp_xf = UsdGeom.Xformable(spawn_point_prim)
                tr = sp_xf.GetTranslateOp()
                if tr:
                    spawn_translate = tr.Get()
                rot = sp_xf.GetRotateXYZOp()
                if rot:
                    spawn_rotate = rot.Get()
                    spawn_rotate_type = "rotateXYZ"
                else:
                    rot = sp_xf.GetRotateYXZOp()
                    if rot:
                        spawn_rotate = rot.Get()
                        spawn_rotate_type = "rotateYXZ"

            # --- Apply transform to capsule (identical to TeleportService) ---
            player_xform = UsdGeom.Xformable(player_prim)

            existing_translate_op = player_xform.GetTranslateOp()
            translate_op = existing_translate_op if existing_translate_op else player_xform.AddTranslateOp()
            translate_op.Set(spawn_translate)

            if spawn_rotate_type == "rotateYXZ":
                rotate_op = player_xform.GetRotateYXZOp()
                if not rotate_op:
                    rotate_op = player_xform.AddRotateYXZOp()
            else:
                rotate_op = player_xform.GetRotateXYZOp()
                if not rotate_op:
                    rotate_op = player_xform.AddRotateXYZOp()
            rotate_op.Set(spawn_rotate)

            existing_scale_op = player_xform.GetScaleOp()
            scale_op = existing_scale_op if existing_scale_op else player_xform.AddScaleOp()
            scale_op.Set(Gf.Vec3d(1.0, 1.0, 1.0))

            player_xform.SetXformOpOrder([translate_op, rotate_op, scale_op])

            # --- Reset camera rotation (identical to TeleportService) ---
            cam_path = f"{player_path}/first_person_camera"
            cam_prim = stage.GetPrimAtPath(cam_path)
            if cam_prim and cam_prim.IsValid():
                cam_xf = UsdGeom.Xformable(cam_prim)
                cam_rot = cam_xf.GetRotateXYZOp()
                if not cam_rot:
                    cam_rot = cam_xf.AddRotateXYZOp()
                cam_rot.Set(Gf.Vec3d(0.0, 0.0, 0.0))

            # --- Reset input controller yaw/pitch ---
            mc = getattr(h, "_movement_controller", None)
            if mc and hasattr(mc, "reset_rotation_state"):
                mc.reset_rotation_state()

            print(f"[player_core] Deferred init applied (rotation: {spawn_rotate[1]:.0f} deg, type={spawn_rotate_type})")

        except Exception as e:
            print(f"[player_core] Deferred init failed: {e}")

        # Ground snap — skip in bird-eye mode (spawn altitude is intentional)
        view_type = getattr(self._h, "_camera_view_type", "firstPerson")
        if view_type != "birdEye":
            try:
                await self.snap_player_to_ground(player_path, frames_wait=3)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Ground snapping (raycast down to find terrain height)
    # ------------------------------------------------------------------

    async def snap_player_to_ground(self, player_path: str, frames_wait: int = 10):
        """
        Cast a ray downward from the player position to find the ground
        and set the player translate Y to ground level.

        Two-pass strategy:
          1. PhysX scene-query raycast (works when colliders exist).
          2. NavMesh closest-point query (works even without colliders).

        The ray starts from the capsule center.  Using report_touch=False
        makes PhysX skip shapes whose interior the ray originates in, so
        the invisible player capsule is ignored.
        """
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom, Gf

            app = kit_app.get_app()
            for _ in range(int(frames_wait)):
                await app.next_update_async()

            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return
            player_prim = stage.GetPrimAtPath(player_path)
            if not player_prim or not player_prim.IsValid():
                return

            xform = UsdGeom.Xformable(player_prim)
            tr_op = xform.GetTranslateOp()
            if not tr_op:
                return
            cur_pos = tr_op.Get()
            if not cur_pos:
                return

            ground_y = self._find_ground_y(
                float(cur_pos[0]), float(cur_pos[1]), float(cur_pos[2]),
                player_path,
            )
            if ground_y is None:
                print("[player_core] snap_to_ground: no ground found, keeping current Y")
                return

            old_y = float(cur_pos[1])
            delta = abs(old_y - ground_y)
            if delta < 1.0:
                return

            tr_op.Set(Gf.Vec3d(float(cur_pos[0]), float(ground_y), float(cur_pos[2])))
            print(f"[player_core] ✓ Snapped to ground: Y {old_y:.1f} → {ground_y:.1f} (Δ{delta:.1f})")
        except Exception as e:
            print(f"[player_core] snap_to_ground failed: {e}")

    def _find_ground_y(self, x: float, y: float, z: float, player_path: str) -> "float | None":
        """
        Return the ground-surface Y at (x, z) by:
          1. PhysX raycast downward (report_touch=False to skip capsule self-hit)
          2. NavMesh closest-point fallback
        """
        ground = self._physx_ground_y(x, y, z, player_path)
        if ground is not None:
            return ground
        ground = self._navmesh_ground_y(x, y, z)
        if ground is not None:
            return ground
        return None

    @staticmethod
    def _physx_ground_y(x: float, y: float, z: float, player_path: str) -> "float | None":
        """PhysX scene-query raycast downward.  Skips player capsule."""
        try:
            import omni.physx
            import carb._carb as _carb_c

            sqi = omni.physx.get_physx_scene_query_interface()
            if not sqi:
                return None

            # Cast from player center — report_touch=False skips shapes the ray
            # starts inside (i.e. the player capsule).
            origin = _carb_c.Float3(float(x), float(y), float(z))
            direction = _carb_c.Float3(0.0, -1.0, 0.0)
            max_dist = 5000.0  # 50 m search

            hit = sqi.raycast_closest(origin, direction, max_dist, False)
            if not hit or not hit.get("hit", False):
                return None

            # Safety: if we still hit the player capsule, ignore
            for k in ("colliderPrimPath", "bodyPrimPath", "primPath", "path"):
                v = hit.get(k)
                if isinstance(v, str) and player_path in v:
                    return None

            hit_pos = hit.get("position")
            if hit_pos is None:
                return None
            try:
                if hasattr(hit_pos, "__getitem__") and len(hit_pos) >= 2:
                    return float(hit_pos[1])
            except Exception:
                pass
            return None
        except Exception:
            return None

    @staticmethod
    def _navmesh_ground_y(x: float, y: float, z: float) -> "float | None":
        """Query NavMesh for the closest walkable point → ground height."""
        try:
            import omni.anim.navigation.core as nav_module
            import carb

            inav = nav_module.acquire_interface()
            if not inav:
                return None
            navmesh = inav.get_navmesh()
            if not navmesh:
                return None

            # find_nearest_point(position, search_extent) → Float3 | None
            if hasattr(navmesh, "find_nearest_point"):
                pt = carb.Float3(float(x), float(y), float(z))
                extent = carb.Float3(500.0, 1000.0, 500.0)
                nearest = navmesh.find_nearest_point(pt, extent)
                if nearest is not None:
                    try:
                        return float(nearest.y) if hasattr(nearest, "y") else float(nearest[1])
                    except Exception:
                        pass
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def retry_bind_viewport_camera(self, cam_path: str, max_frames: int = 120):
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom
            import omni.kit.viewport.utility as vp_utils

            app = kit_app.get_app()
            for _ in range(int(max_frames)):
                stage = _omni_usd.get_context().get_stage()
                cam_ok = False
                try:
                    cam_prim = stage.GetPrimAtPath(cam_path) if stage else None
                    cam_ok = bool(cam_prim and cam_prim.IsValid() and cam_prim.IsA(UsdGeom.Camera))
                except Exception:
                    cam_ok = False
                if cam_ok:
                    vp = vp_utils.get_active_viewport()
                    if vp:
                        try:
                            vp.set_active_camera(cam_path)
                        except Exception:
                            try:
                                vp.camera_path = cam_path
                            except Exception:
                                pass
                    return True
                await app.next_update_async()
        except Exception:
            pass
        return False

    def create_player_character_from_reference(self, spawn_point_prim, spawn_point_path: str):
        h = self._h
        try:
            import omni.usd as _omni_usd
            from pxr import UsdGeom, Gf

            stage = _omni_usd.get_context().get_stage()
            if not stage:
                return None

            from younite.usd_viewer_stage_core_extension.services.core_services.world_conventions import PLAYER_CHARACTER_PATH

            player_path = PLAYER_CHARACTER_PATH

            try:
                existing_prim = stage.GetPrimAtPath(player_path)
                if existing_prim and existing_prim.IsValid():
                    h._player_character_path = player_path
                    return player_path
            except Exception:
                pass

            player_character_usda_path = "Player/player_character.usda"

            root_layer = stage.GetRootLayer()
            root_layer_path = root_layer.identifier
            if root_layer_path:
                root_dir = os.path.dirname(root_layer_path)

                cand_same = os.path.join(root_dir, player_character_usda_path)
                cand_up_one = os.path.join(root_dir, "..", "Player", "player_character.usda")

                cand_from_data = None
                try:
                    probe = root_dir
                    for _ in range(6):
                        base = os.path.basename(probe)
                        if base == "data":
                            cand_from_data = os.path.join(probe, "Player", "player_character.usda")
                            break
                        new_probe = os.path.dirname(probe)
                        if new_probe == probe:
                            break
                        probe = new_probe
                except Exception:
                    cand_from_data = None

                def _norm(p):
                    return os.path.normpath(p).replace("\\", "/") if p else None

                candidates = [_norm(cand_same), _norm(cand_up_one), _norm(cand_from_data)]
                chosen_abs = None
                for c in candidates:
                    if c and os.path.exists(c):
                        chosen_abs = c
                        break

                if chosen_abs:
                    try:
                        rel = os.path.relpath(chosen_abs, start=root_dir).replace("\\", "/")
                        ref_path = rel
                    except Exception:
                        ref_path = chosen_abs
                else:
                    ref_path = player_character_usda_path
            else:
                ref_path = player_character_usda_path

            player_prim = stage.DefinePrim(player_path)
            if not player_prim:
                return None

            player_prim.GetReferences().AddReference(assetPath=ref_path)

            player_prim = stage.GetPrimAtPath(player_path)
            if not player_prim or not player_prim.IsValid():
                h._player_character_path = player_path
                return player_path

            spawn_translate = Gf.Vec3d(0, 0, 0)
            spawn_rotate = Gf.Vec3d(0, 0, 0)
            if spawn_point_prim:
                spawn_transform = UsdGeom.Xformable(spawn_point_prim)
                translate_op = spawn_transform.GetTranslateOp()
                if translate_op:
                    spawn_translate = translate_op.Get()
                rotate_op = spawn_transform.GetRotateXYZOp()
                if not rotate_op:
                    rotate_op = spawn_transform.GetRotateYXZOp()
                if rotate_op:
                    spawn_rotate = rotate_op.Get()

            player_xform = UsdGeom.Xformable(player_prim)
            existing_translate_op = player_xform.GetTranslateOp()
            existing_rotate_op = player_xform.GetRotateXYZOp()
            if not existing_rotate_op:
                existing_rotate_op = player_xform.GetRotateYXZOp()
            existing_scale_op = player_xform.GetScaleOp()

            translate_op = existing_translate_op if existing_translate_op else player_xform.AddTranslateOp()
            translate_op.Set(spawn_translate)

            rotate_op = existing_rotate_op if existing_rotate_op else player_xform.AddRotateXYZOp()
            rotate_op.Set(spawn_rotate)

            scale_op = existing_scale_op if existing_scale_op else player_xform.AddScaleOp()
            scale_op.Set(Gf.Vec3d(1.0, 1.0, 1.0))

            player_xform.SetXformOpOrder([translate_op, rotate_op, scale_op])

            print(f"[player_core] Created PlayerCharacter at {player_path}")

            h._player_character_path = player_path
            return player_path
        except Exception as e:
            print(f"[player_core] Error creating player character: {e}")
            import traceback
            traceback.print_exc()
            return None

