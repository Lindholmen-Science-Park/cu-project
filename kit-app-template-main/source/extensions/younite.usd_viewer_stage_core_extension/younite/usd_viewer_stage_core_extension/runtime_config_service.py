"""
Centralized runtime configuration (side effects).

Keep all \"extra things we do\" (global settings writes, enabling optional extensions)
in one place so the Extension entrypoint stays readable.
"""

from __future__ import annotations


def enable_extension_if_present(ext_name: str) -> bool:
    """Best-effort enable; returns True if we attempted to enable."""
    try:
        import omni.kit.app as kit_app

        app = kit_app.get_app()
        ext_mgr = app.get_extension_manager()
        if hasattr(ext_mgr, "get_extension_path") and ext_mgr.get_extension_path(ext_name):
            ext_mgr.set_extension_enabled_immediate(ext_name, True)
            return True
    except Exception:
        pass
    return False


def enable_optional_extensions() -> None:
    """Enable extensions that improve UX when present."""
    enable_extension_if_present("omni.kit.window.viewport_navigation")
    enable_extension_if_present("omni.kit.streamclient.webrtc")
    enable_extension_if_present("omni.kit.livestream.webrtc")


def apply_streaming_input_settings(settings=None) -> None:
    """Ensure streaming/web viewer forwards input to Kit (keyboard/mouse)."""
    try:
        import carb.settings as carb_settings

        s = settings if settings is not None else carb_settings.get_settings()

        s.set("/app/window/dockKeyboardInput", True)

        s.set("/exts/omni.kit.streamclient.webrtc/transferKeyboardEvents", True)
        s.set("/exts/omni.kit.streamclient.webrtc/transferMouseEvents", True)
        s.set("/exts/omni.kit.streamclient.webrtc/enablePointerLock", True)
        s.set("/exts/omni.kit.streamclient.webrtc/captureKeyboard", True)

        s.set("/exts/omni.kit.streamclient.webrtc/consumeAltKey", True)
        s.set("/exts/omni.kit.streamclient.webrtc/relativeMouse", True)
        s.set("/exts/omni.kit.streamclient.webrtc/focusOnClick", True)

        s.set("/exts/omni.kit.livestream.webrtc/transferKeyboardEvents", True)
        s.set("/exts/omni.kit.livestream.webrtc/transferMouseEvents", True)
        s.set("/exts/omni.kit.livestream.webrtc/captureKeyboard", True)
        s.set("/exts/omni.kit.livestream.webrtc/enablePointerLock", True)
        s.set("/exts/omni.kit.livestream.webrtc/consumeAltKey", True)
        s.set("/exts/omni.kit.livestream.webrtc/relativeMouse", True)
        s.set("/exts/omni.kit.livestream.webrtc/focusOnClick", True)
    except Exception:
        pass


def enable_simulation_loop(settings=None) -> None:
    """Ensure the simulation loop is enabled so physics runs with timeline."""
    try:
        import carb.settings as carb_settings

        s = settings if settings is not None else carb_settings.get_settings()
        s.set("/app/runLoops/mainLoop/simulationEnabled", True)
    except Exception:
        pass


def configure_runtime(*, settings=None) -> None:
    """One-call setup invoked from Extension startup."""
    enable_optional_extensions()
    apply_streaming_input_settings(settings=settings)
    enable_simulation_loop(settings=settings)
    try:
        import carb.settings as carb_settings

        s = settings if settings is not None else carb_settings.get_settings()
        if not s.get("/younite/media/contentTheme"):
            s.set("/younite/media/contentTheme", "horseshow")
    except Exception:
        pass

