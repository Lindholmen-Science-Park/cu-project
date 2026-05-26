from __future__ import annotations

from typing import Optional, Tuple


class ProjectionService:
    """
    Projects USD world positions to viewport pixel coordinates.
    """

    @staticmethod
    def _get_viewport_resolution(viewport_api) -> Optional[Tuple[int, int]]:
        try:
            import carb.settings

            s = carb.settings.get_settings()
            for k_w, k_h in [
                ("/app/renderer/resolution/width", "/app/renderer/resolution/height"),
                ("/renderer/resolution/width", "/renderer/resolution/height"),
            ]:
                try:
                    w = int(s.get(k_w) or 0)
                    h = int(s.get(k_h) or 0)
                    if w > 0 and h > 0:
                        return (w, h)
                except Exception:
                    continue
        except Exception:
            pass
        return None

    @staticmethod
    def _is_in_front_of_camera(world_pos, viewport_api, usd_context) -> Optional[bool]:
        try:
            from pxr import UsdGeom, Gf
        except Exception:
            return None
        try:
            camera_path = getattr(viewport_api, "camera_path", None)
            if not camera_path or not usd_context:
                return None
            stage = usd_context.get_stage()
            if not stage:
                return None
            camera_prim = stage.GetPrimAtPath(camera_path)
            if not camera_prim or not camera_prim.IsValid():
                return None
            xform = UsdGeom.Xformable(camera_prim)
            world_to_camera = xform.ComputeLocalToWorldTransform(0).GetInverse()
            pos = Gf.Vec3d(world_pos[0], world_pos[1], world_pos[2]) if not isinstance(world_pos, Gf.Vec3d) else world_pos
            camera_pos = world_to_camera.Transform(pos)
            return float(camera_pos[2]) < 0.0
        except Exception:
            return None

    def world_to_screen(self, *, world: Tuple[float, float, float], viewport_api, usd_context) -> Tuple[Optional[Tuple[int, int]], bool]:
        try:
            from pxr import Gf
        except Exception:
            return None, False

        res = self._get_viewport_resolution(viewport_api)
        if not res or res[0] <= 0 or res[1] <= 0:
            return None, False
        width, height = res

        pos = Gf.Vec3d(float(world[0]), float(world[1]), float(world[2]))

        try:
            wtndc = getattr(viewport_api, "world_to_ndc", None)
            if wtndc is not None and hasattr(wtndc, "Transform"):
                v = wtndc.Transform(pos)
                ndc_x, ndc_y = float(v[0]), float(v[1])
                in_front = self._is_in_front_of_camera(pos, viewport_api, usd_context)
                if in_front is False:
                    return None, False
                in_view = abs(ndc_x) <= 1.0 and abs(ndc_y) <= 1.0
                x_px = int((ndc_x + 1.0) * 0.5 * width)
                y_px = int((1.0 - ndc_y) * 0.5 * height)
                return (x_px, y_px), bool(in_view)
        except Exception:
            pass

        try:
            from pxr import UsdGeom

            camera_path = getattr(viewport_api, "camera_path", None)
            if not camera_path:
                return None, False
            stage = usd_context.get_stage() if usd_context else None
            if not stage:
                return None, False
            camera_prim = stage.GetPrimAtPath(camera_path)
            if not camera_prim or not camera_prim.IsValid():
                return None, False
            xform = UsdGeom.Xformable(camera_prim)
            world_to_camera = xform.ComputeLocalToWorldTransform(0).GetInverse()
            camera_pos = world_to_camera.Transform(pos)
            if float(camera_pos[2]) >= 0.0:
                return None, False
            camera = UsdGeom.Camera(camera_prim)
            focal_length = float(camera.GetFocalLengthAttr().Get() or 0.0) or 0.0
            h_ap = float(camera.GetHorizontalApertureAttr().Get() or 0.0) or 0.0
            v_ap = float(camera.GetVerticalApertureAttr().Get() or 0.0) or 0.0
            if focal_length == 0.0 or h_ap == 0.0 or v_ap == 0.0:
                return None, False
            aspect = float(width) / float(height)
            ndc_x = -float(camera_pos[0]) / (float(camera_pos[2]) * (h_ap / focal_length) * 0.5)
            ndc_y = -float(camera_pos[1]) / (float(camera_pos[2]) * (v_ap / focal_length) * 0.5 / aspect)
            in_view = abs(ndc_x) <= 1.0 and abs(ndc_y) <= 1.0
            x_px = int((ndc_x + 1.0) * 0.5 * width)
            y_px = int((1.0 - ndc_y) * 0.5 * height)
            return (x_px, y_px), bool(in_view)
        except Exception:
            return None, False

    def is_collider_visible(self, *, prim_path: str, viewport_api, usd_context) -> bool:
        """Check if any corner of a prim's Collider child cube is in the camera frustum."""
        try:
            from pxr import Usd, UsdGeom, Gf
        except Exception:
            return False
        try:
            stage = usd_context.get_stage() if usd_context else None
            if not stage:
                return False
            collider = stage.GetPrimAtPath(f"{prim_path}/Collider")
            if not collider or not collider.IsValid():
                return False

            cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            l2w = cache.GetLocalToWorldTransform(collider)

            corners = [
                Gf.Vec3d(x, y, z)
                for x in (-1.0, 1.0)
                for y in (-1.0, 1.0)
                for z in (-1.0, 1.0)
            ]

            wtndc = getattr(viewport_api, "world_to_ndc", None)
            if wtndc is None or not hasattr(wtndc, "Transform"):
                return False

            for local_pt in corners:
                world_pt = l2w.Transform(local_pt)
                in_front = self._is_in_front_of_camera(
                    (float(world_pt[0]), float(world_pt[1]), float(world_pt[2])),
                    viewport_api, usd_context,
                )
                if in_front is False:
                    continue
                v = wtndc.Transform(world_pt)
                if abs(float(v[0])) <= 1.0 and abs(float(v[1])) <= 1.0:
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def get_anchor_world(stage, prim_path: str) -> Optional[Tuple[float, float, float]]:
        try:
            from pxr import UsdGeom
        except Exception:
            return None
        try:
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                return None
            xformable = UsdGeom.Xformable(prim)
            l2w = xformable.ComputeLocalToWorldTransform(0)
            t = l2w.ExtractTranslation()
            return (float(t[0]), float(t[1]), float(t[2]))
        except Exception:
            return None
