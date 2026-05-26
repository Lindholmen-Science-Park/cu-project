import carb
import omni.kit.viewport.utility as vp_util
import omni.kit.raycast.query as rcq
from pxr import Gf


class RaycastService:
    """Viewport raycast service with sync (PhysX) and async (PhysX + RTX) modes."""

    def __init__(self, raycast_interface):
        self._raycast_interface = raycast_interface

    # ── ray construction ─────────────────────────────────────────────

    def _get_ray_from_ndc(self, ndc_x: float, ndc_y: float):
        """Convert NDC screen coordinates to a world-space ray (origin, direction)."""
        viewport = vp_util.get_active_viewport()
        if not viewport:
            return None, None

        viewport_api = viewport.viewport_api if hasattr(viewport, "viewport_api") else viewport
        ndc_to_world = viewport_api.ndc_to_world

        p_near = ndc_to_world.Transform(Gf.Vec3d(ndc_x, ndc_y, 0.0))
        p_far = ndc_to_world.Transform(Gf.Vec3d(ndc_x, ndc_y, 1.0))

        direction = p_far - p_near
        direction.Normalize()
        return p_near, direction

    # ── public API ───────────────────────────────────────────────────

    def raycast_from_ndc(self, ndc_x: float, ndc_y: float):
        """
        Synchronous raycast (PhysX only — instant, no frame pump).
        Returns (world_pos, normal, meta) or (None, None, {}).
        """
        try:
            p_near, direction = self._get_ray_from_ndc(ndc_x, ndc_y)
            if p_near is None:
                return (None, None, {})

            result = self._physx_raycast(p_near, direction)
            if result[0] is not None:
                return result

            return (None, None, {})
        except Exception:
            return (None, None, {})

    async def raycast_from_ndc_async(self, ndc_x: float, ndc_y: float):
        """
        Non-blocking raycast: PhysX first (instant), RTX if PhysX misses
        (awaits natural frame ticks — never blocks the main thread).
        Returns (world_pos, normal, meta) or (None, None, {}).
        """
        try:
            p_near, direction = self._get_ray_from_ndc(ndc_x, ndc_y)
            if p_near is None:
                return (None, None, {})

            result = self._physx_raycast(p_near, direction)
            if result[0] is not None:
                return result

            if self._raycast_interface:
                result = await self._rtx_raycast_async(p_near, direction)
                if result[0] is not None:
                    return result

            return (None, None, {})
        except Exception:
            return (None, None, {})

    # ── PhysX (synchronous) ──────────────────────────────────────────

    def _physx_raycast(self, origin, direction):
        """Synchronous PhysX scene-query raycast (fast, no frame pump)."""
        try:
            import omni.physx
            import carb._carb as _carb_c

            sqi = omni.physx.get_physx_scene_query_interface()
            if not sqi:
                return (None, None, {})

            origin_f3 = _carb_c.Float3(float(origin[0]), float(origin[1]), float(origin[2]))
            dir_f3 = _carb_c.Float3(float(direction[0]), float(direction[1]), float(direction[2]))
            hit_result = sqi.raycast_closest(origin_f3, dir_f3, 1e6, True)

            if not hit_result or not hit_result.get("hit", False):
                return (None, None, {})

            meta = {}
            if isinstance(hit_result, dict):
                for k in (
                    "collider", "rigidBody",
                    "colliderPrimPath", "bodyPrimPath", "primPath", "path",
                    "collider_path", "body_path", "rigidBodyPrimPath",
                ):
                    v = hit_result.get(k)
                    if isinstance(v, str) and v.strip():
                        meta[k] = v.strip()

            world_pos = self._extract_vec3(hit_result.get("position"))
            normal = self._extract_vec3(hit_result.get("normal"))
            return (world_pos, normal, meta)
        except Exception:
            return (None, None, {})

    # ── RTX (async — non-blocking) ───────────────────────────────────

    async def _rtx_raycast_async(self, origin, direction):
        """Non-blocking RTX raycast — awaits natural frame ticks instead of
        pumping app.update() or sleeping."""
        try:
            import omni.kit.app
            app = omni.kit.app.get_app()

            ray = rcq.Ray(origin=origin, direction=direction, min_t=0.0, max_t=1e6)
            seq_id = self._raycast_interface.add_raycast_sequence()
            try:
                self._raycast_interface.set_raycast_sequence_array_size(seq_id, 1)
                self._raycast_interface.submit_ray_to_raycast_sequence(seq_id, ray)

                for _ in range(3):
                    await app.next_update_async()
                    result, _, hit = (
                        self._raycast_interface.get_latest_result_from_raycast_sequence(seq_id)
                    )
                    if result == rcq.Result.SUCCESS and hit and hit.valid:
                        world_pos = (hit.hit_position[0], hit.hit_position[1], hit.hit_position[2])
                        normal = None
                        if hasattr(hit, "normal") and hit.normal:
                            normal = (hit.normal[0], hit.normal[1], hit.normal[2])
                        meta = {}
                        for attr in (
                            "prim_path", "primPath", "path",
                            "colliderPrimPath", "bodyPrimPath", "rigidBodyPrimPath",
                        ):
                            v = getattr(hit, attr, None)
                            if isinstance(v, str) and v.strip():
                                meta[attr] = v.strip()
                        return (world_pos, normal, meta)
            finally:
                try:
                    self._raycast_interface.remove_raycast_sequence(seq_id)
                except Exception:
                    pass

            return (None, None, {})
        except Exception:
            return (None, None, {})

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_vec3(val):
        """Extract a (x, y, z) tuple from various vector-like objects."""
        if val is None:
            return None
        try:
            if hasattr(val, "__getitem__") and hasattr(val, "__len__") and len(val) >= 3:
                return (float(val[0]), float(val[1]), float(val[2]))
        except (IndexError, TypeError, ValueError):
            pass
        return None
