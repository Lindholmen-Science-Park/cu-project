"""
Shared edit layer manager: creates / loads / saves the persistent
usd_edits.usda sublayer used by both vertex editing and prim transforms.
"""

import os

EDIT_LAYER_FILENAME = "usd_edits.usda"
EDIT_LAYER_SUBDIR = "sublayers"


def _get_stage():
    try:
        import omni.usd
        ctx = omni.usd.get_context()
        return ctx.get_stage() if ctx else None
    except Exception:
        return None


class EditLayerManager:
    def __init__(self):
        self._edit_layer = None

    @property
    def edit_layer(self):
        return self._edit_layer

    def get_edit_layer_path(self):
        stage = _get_stage()
        if not stage:
            return None
        root_layer = stage.GetRootLayer()
        if not root_layer or not root_layer.realPath:
            return None
        root_dir = os.path.dirname(root_layer.realPath)
        return os.path.join(root_dir, EDIT_LAYER_SUBDIR, EDIT_LAYER_FILENAME).replace("\\", "/")

    def ensure_edit_layer(self):
        """Find or create the edit sublayer and insert it into the stage."""
        if self._edit_layer:
            return self._edit_layer

        from pxr import Sdf

        stage = _get_stage()
        if not stage:
            return None

        edit_path = self.get_edit_layer_path()
        if not edit_path:
            return None

        edit_layer = Sdf.Layer.FindOrOpen(edit_path)
        if not edit_layer:
            edit_layer = Sdf.Layer.CreateNew(edit_path)
            print(f"[usd_edit] created edit layer: {edit_path}")

        root_layer = stage.GetRootLayer()
        rel_path = "./" + EDIT_LAYER_SUBDIR + "/" + EDIT_LAYER_FILENAME
        paths = list(root_layer.subLayerPaths)
        if rel_path not in paths and edit_path not in paths:
            root_layer.subLayerPaths.insert(0, rel_path)
            print("[usd_edit] inserted edit sublayer into stage")

        self._edit_layer = edit_layer
        return edit_layer

    def load_existing_edit_layer(self):
        """Called on startup to auto-load an existing edit sublayer if present."""
        edit_path = self.get_edit_layer_path()
        if not edit_path:
            return
        if os.path.exists(edit_path):
            self.ensure_edit_layer()
            print(f"[usd_edit] auto-loaded edit layer: {edit_path}")

    def save_layer(self):
        """Persist the edit layer to disk."""
        if self._edit_layer:
            self._edit_layer.Save()

    def clear_layer(self):
        """Erase all content from the edit layer and save."""
        if self._edit_layer:
            self._edit_layer.Clear()
            self._edit_layer.Save()
            print("[usd_edit] edit layer cleared (hard reset)")

    @property
    def has_edit_layer_file(self) -> bool:
        edit_path = self.get_edit_layer_path()
        return edit_path is not None and os.path.exists(edit_path)
