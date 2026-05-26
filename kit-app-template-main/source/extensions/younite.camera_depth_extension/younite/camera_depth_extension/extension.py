"""
Camera Depth Extension.

Listens for ``cameraDepthRequest`` (bridged by messaging_core_extension).
Payload:
    { "action": "capture" }              -- raycast depth and create/update the point cloud
    { "action": "detect_obstacles" }     -- analyse point cloud, create NavMesh obstacle areas, rebake
    { "action": "clear" }                -- remove point cloud AND obstacle areas, rebake
    { "action": "toggle_points", "visible": bool }   -- show/hide point cloud

Area visibility is handled by the bake orchestrator via
``showCameraDepthAreasRequest`` (same pattern as camera frustum areas).

Responds with ``cameraDepthStatus``:
    { "status": ..., "pointCount": int, "obstacleCount": int,
      "pointsVisible": bool, "error": str }
"""

import asyncio

import omni.ext
import omni.kit.app

CAMERA_PRIM_PATH = "/World/sensor_camera_01"
POINTS_PRIM_PATH = "/World/SensorPointCloud"

_LOG = "[camera_depth]"


def _to_bool(value, default: bool = True) -> bool:
    """Robust bool conversion — handles strings from the messaging bridge."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(value)


class CameraDepthExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        print(f"{_LOG} on_startup")
        self._ext_id = ext_id
        self._subs = []
        self._capturing = False
        self._capture_task = None
        self._points_visible = True

        try:
            import carb.eventdispatcher
            import carb.events
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("cameraDepthRequest"),
                    "cameraDepthRequest",
                )
            except Exception:
                pass

            def _on_request(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                action = (payload.get("action") or "").strip().lower()
                print(f"{_LOG} request: action={action}")
                if action == "capture":
                    self._do_capture()
                elif action == "detect_obstacles":
                    self._do_detect_obstacles()
                elif action == "clear":
                    self._do_clear()
                elif action == "toggle_points":
                    visible = _to_bool(payload.get("visible"), True)
                    self._do_toggle_points(visible)

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.camera_depth_extension/cameraDepthRequest",
                    event_name="cameraDepthRequest",
                    on_event=_on_request,
                    order=0,
                )
            )
            print(f"{_LOG} subscribed to cameraDepthRequest")
        except Exception as e:
            print(f"{_LOG} subscribe failed: {e}")

    def on_shutdown(self):
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()

    # -- Dispatch helpers --

    def _dispatch_status(self, status: str, point_count: int = 0,
                         obstacle_count: int = 0, error: str = ""):
        from younite.messaging_core_extension.message_utils import dispatch_to_events2
        dispatch_to_events2("cameraDepthStatus", {
            "status": status,
            "pointCount": point_count,
            "obstacleCount": obstacle_count,
            "pointsVisible": self._points_visible,
            "error": error,
        })

    def _dispatch_rebake(self):
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2
            dispatch_to_events2("navmeshRebakeRequest", {})
        except Exception as e:
            print(f"{_LOG} rebake dispatch failed: {e}")

    # -- Visibility helpers --

    def _set_prim_visible(self, prim_path: str, visible: bool):
        from younite.payload_orchestrator_core_extension import show_hide, Priority
        if show_hide(prim_path, visible, Priority.MEDIUM, source="camera_depth"):
            print(f"{_LOG} set_prim_visible({prim_path}, {visible}) -> orchestrator")
            return
        try:
            import omni.usd
            from pxr import UsdGeom
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            prim = stage.GetPrimAtPath(prim_path)
            if prim and prim.IsValid():
                img = UsdGeom.Imageable(prim)
                if visible:
                    img.MakeVisible()
                else:
                    img.MakeInvisible()
        except Exception as e:
            print(f"{_LOG} set_prim_visible({prim_path}, {visible}) failed: {e}")

    # -- Actions --

    def _do_capture(self):
        if self._capturing:
            return
        self._capturing = True
        self._dispatch_status("capturing")

        async def _run():
            try:
                import omni.usd
                from .obstacle_detection import remove_obstacle_areas, has_obstacle_areas

                had_obstacles = has_obstacle_areas()

                stage = omni.usd.get_context().get_stage()
                if stage:
                    old = stage.GetPrimAtPath(POINTS_PRIM_PATH)
                    if old and old.IsValid():
                        stage.RemovePrim(POINTS_PRIM_PATH)
                        print(f"{_LOG} cleared previous point cloud")

                remove_obstacle_areas()

                if had_obstacles:
                    self._dispatch_rebake()

                self._points_visible = True

                from .depth_capture import capture_depth_pointcloud
                count = await capture_depth_pointcloud(CAMERA_PRIM_PATH, POINTS_PRIM_PATH)
                print(f"{_LOG} created {count} points at {POINTS_PRIM_PATH}")
                self._dispatch_status("done", point_count=count)
            except Exception as e:
                print(f"{_LOG} capture failed: {e}")
                import traceback
                traceback.print_exc()
                self._dispatch_status("error", error=str(e))
            finally:
                self._capturing = False

        self._capture_task = asyncio.ensure_future(_run())

    def _do_detect_obstacles(self):
        if self._capturing:
            return
        self._capturing = True
        self._dispatch_status("detecting")

        async def _run():
            try:
                from .obstacle_detection import detect_and_create_areas
                count = await detect_and_create_areas(POINTS_PRIM_PATH)
                print(f"{_LOG} created {count} obstacle area(s)")

                if count > 0:
                    self._dispatch_rebake()

                self._dispatch_status("obstacles_done", obstacle_count=count)
            except Exception as e:
                print(f"{_LOG} obstacle detection failed: {e}")
                import traceback
                traceback.print_exc()
                self._dispatch_status("error", error=str(e))
            finally:
                self._capturing = False

        self._capture_task = asyncio.ensure_future(_run())

    def _do_clear(self):
        try:
            import omni.usd
            stage = omni.usd.get_context().get_stage()

            prim = stage.GetPrimAtPath(POINTS_PRIM_PATH)
            if prim and prim.IsValid():
                stage.RemovePrim(POINTS_PRIM_PATH)
                print(f"{_LOG} cleared {POINTS_PRIM_PATH}")

            from .obstacle_detection import remove_obstacle_areas, has_obstacle_areas
            had_obstacles = has_obstacle_areas()
            remove_obstacle_areas()

            self._points_visible = True
            self._dispatch_status("cleared")

            if had_obstacles:
                self._dispatch_rebake()
        except Exception as e:
            print(f"{_LOG} clear failed: {e}")
            self._dispatch_status("error", error=str(e))

    def _do_toggle_points(self, visible: bool):
        self._points_visible = visible
        self._set_prim_visible(POINTS_PRIM_PATH, visible)
        print(f"{_LOG} point cloud visibility: {visible}")
        self._dispatch_status("toggle_update")
