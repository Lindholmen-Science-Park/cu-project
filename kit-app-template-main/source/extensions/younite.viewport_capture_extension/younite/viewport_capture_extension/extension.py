"""
Viewport Capture Extension.

Listens for ``viewportCaptureRequest`` (bridged by messaging_core_extension).
Payload:
    { "format": "jpeg" }   -- optional, defaults to jpeg; also supports "png"

Captures the Kit viewport at full GPU resolution into an in-memory buffer,
encodes it as JPEG/PNG via PIL, and serves it through a lightweight HTTP
endpoint for the web client to download directly.

Only the download URL is sent through the WebRTC data channel (well within
the 64 KB NVST message limit).

Result:
    { "status": "ready", "port": int, "captureId": str, "filename": str,
      "width": int, "height": int }

Error:
    { "status": "error", "error": str }

Progress:
    { "status": "capturing" }
"""

import asyncio
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

import omni.ext
import omni.kit.app

_LOG = "[viewport_capture]"
_CAPTURE_PORT = 49300
_CAPTURE_TTL = 120


class _CaptureStore:
    """Thread-safe in-memory store for captured images with TTL cleanup."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items: dict = {}

    def put(self, capture_id: str, data: bytes, content_type: str, filename: str):
        with self._lock:
            self._items[capture_id] = {
                "bytes": data,
                "content_type": content_type,
                "filename": filename,
                "created": time.time(),
            }

    def pop(self, capture_id: str):
        with self._lock:
            return self._items.pop(capture_id, None)

    def cleanup(self, ttl: float = _CAPTURE_TTL):
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._items.items() if now - v["created"] > ttl]
            for k in expired:
                del self._items[k]


_store = _CaptureStore()


class _CaptureHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        capture_id = self.path.lstrip("/")
        item = _store.pop(capture_id)
        if item:
            self.send_response(200)
            self.send_header("Content-Type", item["content_type"])
            self.send_header("Content-Disposition", f'attachment; filename="{item["filename"]}"')
            self.send_header("Content-Length", str(len(item["bytes"])))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(item["bytes"])
        else:
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def log_message(self, format, *args):
        pass


class ViewportCaptureExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        print(f"{_LOG} on_startup")
        self._ext_id = ext_id
        self._subs = []
        self._capturing = False
        self._capture_task = None
        self._http_server = None
        self._http_thread = None

        self._start_http_server()

        try:
            import carb.eventdispatcher
            import carb.events
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()
            try:
                omni.kit.app.register_event_alias(
                    carb.events.type_from_string("viewportCaptureRequest"),
                    "viewportCaptureRequest",
                )
            except Exception:
                pass

            def _on_request(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                fmt = (payload.get("format") or "jpeg").strip().lower()
                if fmt not in ("jpeg", "png"):
                    fmt = "jpeg"
                print(f"{_LOG} capture request: format={fmt}")
                self._do_capture(fmt)

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.viewport_capture_extension/viewportCaptureRequest",
                    event_name="viewportCaptureRequest",
                    on_event=_on_request,
                    order=0,
                )
            )
            print(f"{_LOG} subscribed to viewportCaptureRequest")
        except Exception as e:
            print(f"{_LOG} subscribe failed: {e}")

    def on_shutdown(self):
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._stop_http_server()

    def _start_http_server(self):
        try:
            self._http_server = HTTPServer(("0.0.0.0", _CAPTURE_PORT), _CaptureHandler)
            self._http_thread = threading.Thread(target=self._http_server.serve_forever, daemon=True)
            self._http_thread.start()
            print(f"{_LOG} HTTP server started on port {_CAPTURE_PORT}")
        except Exception as e:
            print(f"{_LOG} HTTP server failed to start: {e}")

    def _stop_http_server(self):
        if self._http_server:
            self._http_server.shutdown()
            self._http_server = None
        if self._http_thread:
            self._http_thread.join(timeout=2)
            self._http_thread = None

    def _dispatch(self, payload: dict):
        from younite.messaging_core_extension.message_utils import dispatch_to_events2
        dispatch_to_events2("viewportCaptureResult", payload)

    def _do_capture(self, fmt: str):
        if self._capturing:
            print(f"{_LOG} capture already in progress, ignoring")
            return
        self._capturing = True
        self._dispatch({"status": "capturing"})
        _store.cleanup()

        async def _run():
            try:
                import ctypes
                import io
                import base64
                from PIL import Image
                from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_buffer

                viewport = get_active_viewport()
                if not viewport:
                    self._dispatch({"status": "error", "error": "No active viewport"})
                    return

                future = asyncio.get_event_loop().create_future()

                def _on_buffer(buffer, buffer_size, width, height, pixel_format):
                    try:
                        ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
                        ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
                        ptr = ctypes.pythonapi.PyCapsule_GetPointer(buffer, None)
                        raw = bytes((ctypes.c_ubyte * buffer_size).from_address(ptr))
                        future.set_result((raw, width, height))
                    except Exception as e:
                        future.set_exception(e)

                capture_viewport_to_buffer(viewport, _on_buffer)
                raw_rgba, w, h = await future

                img = Image.frombytes("RGBA", (w, h), raw_rgba)
                buf = io.BytesIO()
                if fmt == "png":
                    img.save(buf, format="PNG")
                    content_type = "image/png"
                    ext = "png"
                else:
                    img.convert("RGB").save(buf, format="JPEG", quality=95)
                    content_type = "image/jpeg"
                    ext = "jpg"
                image_bytes = buf.getvalue()

                capture_id = uuid.uuid4().hex[:12]
                filename = f"rendered_{w}x{h}_{int(time.time())}.{ext}"
                _store.put(capture_id, image_bytes, content_type, filename)

                print(f"{_LOG} captured {len(image_bytes)} bytes, {w}x{h}, ready at /{capture_id}")

                self._dispatch({
                    "status": "ready",
                    "port": _CAPTURE_PORT,
                    "captureId": capture_id,
                    "filename": filename,
                    "width": w,
                    "height": h,
                })

            except Exception as e:
                print(f"{_LOG} capture failed: {e}")
                import traceback
                traceback.print_exc()
                self._dispatch({"status": "error", "error": str(e)})
            finally:
                self._capturing = False

        self._capture_task = asyncio.ensure_future(_run())
