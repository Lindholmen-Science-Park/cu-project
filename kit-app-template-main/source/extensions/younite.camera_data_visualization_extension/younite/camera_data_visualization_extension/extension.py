"""
Camera Data Visualization Extension.

Listens to cameraDataVisualizationRequest (bridged by younite.messaging_core_extension).
Payload: { action: "start" | "stop", mode: "heatmap" | "tracker" }

Heatmap and sphere tracker can be toggled independently.
Both visualize data from the "Main Exit" camera's ground footprint.
"""

from pathlib import Path
from typing import Optional

import omni.ext
import omni.kit.app

TARGET_CAMERA_PRIM = "/World/camera_main_entrance_exit"
TARGET_CAMERA_ID = "camera_main_entrance_exit"


class CameraDataVisualizationExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        print("[camera_data_viz] on_startup called")
        self._ext_id = ext_id
        self._subs = []
        self._heatmap_active = False
        self._tracker_active = False
        self._footprint = None
        self._detection_map = None
        self._data_path: Optional[Path] = None

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()
            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("cameraDataVisualizationRequest"),
                    "cameraDataVisualizationRequest",
                )
            except Exception:
                pass

            def _on_request(evt):
                print("[camera_data_viz] request received")
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                action = (payload.get("action") or "").strip().lower()
                mode = (payload.get("mode") or "").strip().lower()
                if not mode or mode not in ("heatmap", "tracker"):
                    return
                if action == "start":
                    self._start_mode(mode)
                elif action == "stop":
                    self._stop_mode(mode)

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.camera_data_visualization_extension/cameraDataVisualizationRequest",
                    event_name="cameraDataVisualizationRequest",
                    on_event=_on_request,
                    order=0,
                )
            )
            print("[camera_data_viz] subscribed to cameraDataVisualizationRequest")
        except Exception as e:
            print(f"[camera_data_viz] subscribe failed: {e}")

    def on_shutdown(self):
        try:
            if self._heatmap_active:
                self._stop_mode("heatmap")
            if self._tracker_active:
                self._stop_mode("tracker")
        except Exception:
            pass
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._heatmap_active = False
        self._tracker_active = False
        self._footprint = None
        self._detection_map = None

    def _get_extension_data_path(self) -> Path:
        if self._data_path is not None and self._data_path.exists():
            return self._data_path
        try:
            app = omni.kit.app.get_app()
            ext_mgr = app.get_extension_manager()
            if hasattr(ext_mgr, "get_extension_path"):
                ext_path = ext_mgr.get_extension_path(self._ext_id)
                if ext_path:
                    p = Path(ext_path) / "data"
                    if p.exists():
                        self._data_path = p
                        return self._data_path
        except Exception:
            pass
        fallback = Path(__file__).resolve().parent.parent.parent / "data"
        self._data_path = fallback
        return self._data_path

    def _ensure_footprint(self):
        """Compute and cache the camera's ground footprint (lazy, requires PhysX)."""
        if self._footprint is not None:
            return self._footprint
        try:
            from .camera_footprint import compute_camera_footprint
            self._footprint = compute_camera_footprint(TARGET_CAMERA_PRIM)
            if self._footprint:
                print(f"[camera_data_viz] Footprint computed for {TARGET_CAMERA_ID}")
            else:
                print(f"[camera_data_viz] Failed to compute footprint for {TARGET_CAMERA_ID}")
        except Exception as e:
            print(f"[camera_data_viz] Footprint computation error: {e}")
            self._footprint = None
        return self._footprint

    def _scan_detection_bounds(self, json_path: Path):
        """Scan MQTT JSON for detection x,y coordinate range."""
        import json
        try:
            with json_path.open("r", encoding="utf-8") as f:
                messages = json.load(f)
        except Exception as e:
            print(f"[camera_data_viz] Failed to read {json_path}: {e}")
            return None

        all_x, all_y = [], []
        for msg in messages:
            topic = msg.get("topic", "")
            if "dataq/detections/" not in topic and "dataq/tracker/" not in topic:
                continue
            payload_parsed = msg.get("payload_parsed", {})
            detection_list = payload_parsed.get("list", [])
            if not isinstance(detection_list, list):
                continue
            for det in detection_list:
                if not isinstance(det, dict):
                    continue
                if det.get("class") != "Human" or det.get("ignore", False):
                    continue
                if "x" in det and "y" in det:
                    try:
                        all_x.append(float(det["x"]))
                        all_y.append(float(det["y"]))
                    except (ValueError, TypeError):
                        pass

        if not all_x:
            print("[camera_data_viz] No detection points found in data")
            return None

        pad_x = max(0.5, (max(all_x) - min(all_x)) * 0.05)
        pad_y = max(0.5, (max(all_y) - min(all_y)) * 0.05)
        bounds = (min(all_x) - pad_x, max(all_x) + pad_x,
                  min(all_y) - pad_y, max(all_y) + pad_y)
        print(f"[camera_data_viz] Detection bounds from {len(all_x)} points: "
              f"x=[{bounds[0]:.2f}, {bounds[1]:.2f}], y=[{bounds[2]:.2f}, {bounds[3]:.2f}]")
        return bounds

    def _ensure_detection_map(self):
        """Compute and cache the detection-to-world raycast mapping grid."""
        if self._detection_map is not None:
            return self._detection_map

        data_dir = self._get_extension_data_path()
        json_path = data_dir / "mqtt_messages.json"
        if not json_path.exists():
            print(f"[camera_data_viz] No MQTT data at {json_path}")
            return None

        det_bounds = self._scan_detection_bounds(json_path)
        if not det_bounds:
            return None

        try:
            from .camera_footprint import build_detection_map
            self._detection_map = build_detection_map(TARGET_CAMERA_PRIM, det_bounds, grid_res=64)
            if self._detection_map:
                print(f"[camera_data_viz] Detection map built for {TARGET_CAMERA_ID}")
            else:
                print(f"[camera_data_viz] Failed to build detection map for {TARGET_CAMERA_ID}")
        except Exception as e:
            print(f"[camera_data_viz] Detection map error: {e}")
            import traceback
            traceback.print_exc()
            self._detection_map = None
        return self._detection_map

    def _start_mode(self, mode: str):
        from younite.messaging_core_extension.message_utils import dispatch_to_events2

        footprint = self._ensure_footprint()
        if not footprint:
            print(f"[camera_data_viz] Cannot start {mode}: no footprint available")
            return

        detection_map = self._ensure_detection_map()
        if not detection_map:
            print(f"[camera_data_viz] Warning: no detection map, positions will be approximate")

        data_dir = self._get_extension_data_path()
        default_json = data_dir / "mqtt_messages.json"

        try:
            if mode == "heatmap":
                if self._heatmap_active:
                    return
                from .heatmap_runner import main as heatmap_main
                heatmap_main(
                    camera_id=TARGET_CAMERA_ID,
                    data_source=None,
                    default_data_path=default_json,
                    texture_dir=data_dir,
                    footprint=footprint,
                    detection_map=detection_map,
                )
                self._heatmap_active = True
                print(f"[camera_data_viz] Heatmap started for {TARGET_CAMERA_ID}")
                dispatch_to_events2("cameraDataVisualizationHeatmapStatus", {"active": True})

            elif mode == "tracker":
                if self._tracker_active:
                    return
                from .playback_runner import main as playback_main
                playback_main(
                    camera_id=TARGET_CAMERA_ID,
                    data_source=None,
                    default_data_path=default_json,
                    footprint=footprint,
                    detection_map=detection_map,
                )
                self._tracker_active = True
                print(f"[camera_data_viz] Sphere tracker started for {TARGET_CAMERA_ID}")
                dispatch_to_events2("cameraDataVisualizationTrackerStatus", {"active": True})

        except Exception as e:
            print(f"[camera_data_viz] Failed to start {mode}: {e}")
            import traceback
            traceback.print_exc()

    def _stop_mode(self, mode: str):
        from younite.messaging_core_extension.message_utils import dispatch_to_events2

        try:
            if mode == "heatmap":
                if not self._heatmap_active:
                    return
                from .heatmap_runner import stop_heatmap
                stop_heatmap()
                self._heatmap_active = False
                print("[camera_data_viz] Heatmap stopped")
                dispatch_to_events2("cameraDataVisualizationHeatmapStatus", {"active": False})

            elif mode == "tracker":
                if not self._tracker_active:
                    return
                from .playback_runner import stop_playback
                stop_playback()
                self._tracker_active = False
                print("[camera_data_viz] Sphere tracker stopped")
                dispatch_to_events2("cameraDataVisualizationTrackerStatus", {"active": False})

        except Exception as e:
            print(f"[camera_data_viz] Failed to stop {mode}: {e}")
