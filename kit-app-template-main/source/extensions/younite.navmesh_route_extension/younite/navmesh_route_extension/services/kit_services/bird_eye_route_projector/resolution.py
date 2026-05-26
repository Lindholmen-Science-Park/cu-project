"""Renderer resolution for NDC → pixel mapping."""

from __future__ import annotations

from typing import Optional, Tuple


def get_renderer_resolution() -> Optional[Tuple[int, int]]:
    try:
        import carb.settings

        s = carb.settings.get_settings()
        for k_w, k_h in [
            ("/app/renderer/resolution/width", "/app/renderer/resolution/height"),
            ("/renderer/resolution/width", "/renderer/resolution/height"),
        ]:
            w = int(s.get(k_w) or 0)
            h = int(s.get(k_h) or 0)
            if w > 0 and h > 0:
                return (w, h)
    except Exception:
        pass
    return None
