import math

MIN_RESOLUTION = (640, 360)
MAX_RESOLUTION = (1920, 1440)
WIDTH_ALIGNMENT = 32

# Maximum vertical FOV (degrees) allowed in portrait orientation.
# The camera's aperture is narrowed on the session layer so the scene
# looks natural instead of fish-eye.  Landscape is unaffected.
MAX_VFOV_DEG = 55.0

_DEFAULT_H_APERTURE = 20.955   # USD Camera schema default (mm)
_DEFAULT_V_APERTURE = 15.2908


def _clamp_even(value: float, min_value: int, max_value: int) -> int:
    clamped = int(round(value))
    clamped = max(min_value, min(max_value, clamped))
    return clamped if clamped % 2 == 0 else clamped - 1


def _clamp_width_aligned(value: float, min_value: int, max_value: int) -> int:
    clamped = int(round(value))
    clamped = max(min_value, min(max_value, clamped))
    return (clamped // WIDTH_ALIGNMENT) * WIDTH_ALIGNMENT


class ResolutionService:
    """Handles runtime resolution change requests and portrait FOV capping."""

    def __init__(self, *, settings):
        self._settings = settings
        self._subs = []
        self._render_width = 0
        self._render_height = 0
        self._cam_originals: dict[str, tuple[float, float, float]] = {}

    def start(self):
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                try:
                    self._subs.append(
                        ed.observe_event(
                            observer_name=f"younite.usd_viewer_stage_core_extension/{name}",
                            event_name=name,
                            on_event=handler,
                            order=0,
                        )
                    )
                except Exception:
                    pass

            _observe("changeResolutionRequest", self._on_change_resolution_request)
            _observe("younite.camera.viewTypeChanged", self._on_camera_changed)
            _observe("fixedCameraStatus", self._on_camera_changed)
            _observe("scene.loaded", self._on_camera_changed)
        except Exception:
            pass

    def stop(self):
        self._subs.clear()
        self._cam_originals.clear()

    def _on_camera_changed(self, _event):
        """Re-apply portrait FOV cap when the active camera or scene changes."""
        self._adjust_portrait_fov()

    def _on_change_resolution_request(self, event):
        """
        Payload: { width: number, height: number }
        """
        try:
            if not self._settings:
                return
            from younite.messaging_core_extension.message_utils import normalize_event_payload
            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            width = float(payload.get("width", 0))
            height = float(payload.get("height", 0))
            if width <= 0 or height <= 0:
                return

            target_width = _clamp_width_aligned(width, MIN_RESOLUTION[0], MAX_RESOLUTION[0])
            target_height = _clamp_even(height, MIN_RESOLUTION[1], MAX_RESOLUTION[1])

            try:
                self._settings.set("/app/window/width", int(target_width))
                self._settings.set("/app/window/height", int(target_height))
                self._settings.set("/app/renderer/resolution/width", int(target_width))
                self._settings.set("/app/renderer/resolution/height", int(target_height))
            except Exception:
                pass

            self._render_width = int(target_width)
            self._render_height = int(target_height)
            self._adjust_portrait_fov()

            try:
                import carb.eventdispatcher as _ed
                _ed.get_eventdispatcher().dispatch_event(
                    "changeResolutionConfirmation",
                    {
                        "result": "success",
                        "width": int(target_width),
                        "height": int(target_height),
                        "resolution": f"{int(target_width)}x{int(target_height)}",
                    },
                )
            except Exception:
                pass
        except Exception:
            try:
                import carb.eventdispatcher as _ed
                _ed.get_eventdispatcher().dispatch_event(
                    "changeResolutionConfirmation",
                    {"result": "error", "error": "failed to change resolution"},
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Portrait FOV cap — narrow aperture on session layer
    # ------------------------------------------------------------------

    def _adjust_portrait_fov(self):
        """Narrow the active camera's aperture on the session layer to cap
        vertical FOV at MAX_VFOV_DEG when the render target is portrait.
        Clears the overrides for landscape so the original values apply.
        """
        try:
            w, h = self._render_width, self._render_height
            if w <= 0 or h <= 0:
                return

            import omni.usd
            from pxr import UsdGeom, Usd
            from omni.kit.viewport.utility import get_active_viewport

            viewport = get_active_viewport()
            if not viewport:
                return
            cam_path = str(viewport.camera_path)
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            cam_prim = stage.GetPrimAtPath(cam_path)
            if not cam_prim or not cam_prim.IsValid():
                return
            camera = UsdGeom.Camera(cam_prim)

            if cam_path not in self._cam_originals:
                self._cam_originals[cam_path] = (
                    float(camera.GetFocalLengthAttr().Get() or 18.0),
                    float(camera.GetHorizontalApertureAttr().Get() or _DEFAULT_H_APERTURE),
                    float(camera.GetVerticalApertureAttr().Get() or _DEFAULT_V_APERTURE),
                )
            orig_focal, orig_h_ap, _orig_v_ap = self._cam_originals[cam_path]

            session = stage.GetSessionLayer()

            if h <= w:
                with Usd.EditContext(stage, Usd.EditTarget(session)):
                    camera.GetHorizontalApertureAttr().Clear()
                    camera.GetVerticalApertureAttr().Clear()
                return

            half_hfov = math.atan(orig_h_ap / (2.0 * orig_focal))
            vfov_deg = math.degrees(2.0 * math.atan(math.tan(half_hfov) * float(h) / float(w)))

            if vfov_deg <= MAX_VFOV_DEG:
                with Usd.EditContext(stage, Usd.EditTarget(session)):
                    camera.GetHorizontalApertureAttr().Clear()
                    camera.GetVerticalApertureAttr().Clear()
                return

            max_half_vfov = math.radians(MAX_VFOV_DEG / 2.0)
            aspect = float(w) / float(h)
            new_v_ap = 2.0 * orig_focal * math.tan(max_half_vfov)
            new_h_ap = new_v_ap * aspect

            with Usd.EditContext(stage, Usd.EditTarget(session)):
                camera.GetHorizontalApertureAttr().Set(float(new_h_ap))
                camera.GetVerticalApertureAttr().Set(float(new_v_ap))

            print(
                f"[resolution] portrait FOV cap: h_ap {orig_h_ap:.1f}->{new_h_ap:.1f}, "
                f"vFOV {vfov_deg:.0f}->{MAX_VFOV_DEG}"
            )
        except Exception as e:
            try:
                print(f"[resolution] FOV adjust failed: {e}")
            except Exception:
                pass
