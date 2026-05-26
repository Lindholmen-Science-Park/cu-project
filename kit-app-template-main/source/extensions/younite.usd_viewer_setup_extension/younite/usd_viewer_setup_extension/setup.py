# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import asyncio
from pathlib import Path

import carb.settings
import carb.tokens
import omni.ext
import omni.kit.app
import omni.kit.imgui as _imgui
from omni.kit.mainwindow import get_main_window
from omni.kit.quicklayout import QuickLayout
from omni.kit.viewport.utility import get_viewport_from_window_name


async def _load_layout(layout_file: str):
    """Loads a provided layout file and ensures the viewport is set to FILL."""
    await omni.kit.app.get_app().next_update_async()
    QuickLayout.load_file(layout_file)

    # Set viewport to FILL
    viewport_api = get_viewport_from_window_name("Viewport")
    if viewport_api and hasattr(viewport_api, "fill_frame"):
        viewport_api.fill_frame = True


class SetupExtension(omni.ext.IExt):
    """Extension that sets up the USD Viewer application."""
    def on_startup(self, _ext_id: str):
        """This is called every time the extension is activated. It is used to
        set up the application and load the stage."""
        # Track tasks so we can cancel on shutdown/reload (initialize early; warmup mode returns early)
        self._await_layout = None
        self._load_layout_task = None
        self._imgui_style_pushed = False

        self._settings = carb.settings.get_settings()
        if self._settings and self._settings.get("/app/warmupMode"):
            # if warmup mode is enabled, we don't want to load the stage just return
            return

        # Force-disable the PhysX "Physics Authoring" toolbar (pill).
        # omni.physx.supportui watches this setting and will tear down its
        # ActionBar via _action_bar_enabled_changed → remove_action_bar().
        if self._settings:
            self._settings.set("/persistent/physics/supportUiActionBarEnabled", False)

        try:
            self._await_layout = asyncio.ensure_future(self._delayed_layout())
        except Exception:
            self._await_layout = None
        get_main_window().get_main_menu_bar().visible = False

    async def _delayed_layout(self):
        """This function is used to delay the layout loading until the
        application has finished its initial setup."""
        main_menu_bar = get_main_window().get_main_menu_bar()
        main_menu_bar.visible = False
        # few frame delay to allow automatic Layout of window that want their
        # own positions
        app = omni.kit.app.get_app()
        for _ in range(4):
            await app.next_update_async()  # type: ignore

        settings = carb.settings.get_settings()
        # setup the Layout for your app
        token = "${younite.usd_viewer_setup_extension}/layouts"

        layouts_path = carb.tokens.get_tokens_interface().resolve(token)
        layout_name = settings.get("/app/layout/name")
        layout_file = Path(layouts_path).joinpath(f"{layout_name}.json")

        try:
            self._load_layout_task = asyncio.ensure_future(_load_layout(f"{layout_file}"))
        except Exception:
            self._load_layout_task = None

        # PhysX UI extensions are loaded at startup (required by CCT) but their
        # windows are not wanted in the streaming viewer.  Hide everything
        # except the Viewport after the layout settles.
        try:
            self._hide_non_viewport_task = asyncio.ensure_future(self._hide_non_viewport_windows())
        except Exception:
            self._hide_non_viewport_task = None

        # using imgui directly to adjust some color and Variable
        imgui = _imgui.acquire_imgui()

        # DockSplitterSize is the variable that drive the size of the
        # Dock Split connection
        try:
            imgui.push_style_var_float(_imgui.StyleVar.DockSplitterSize, 2)
            self._imgui_style_pushed = True
        except Exception:
            self._imgui_style_pushed = False

    async def _hide_non_viewport_windows(self):
        """Hide all omni.ui windows except Viewport and strip the viewport menubar.

        Runs multiple passes because PhysX UI extensions create windows
        asynchronously (some appear only after CCT activation).
        """
        app = omni.kit.app.get_app()
        for _ in range(8):
            await app.next_update_async()
        self._do_hide_pass()
        self._hide_viewport_menubar()

        for _ in range(5):
            for _ in range(30):
                await app.next_update_async()
            self._do_hide_pass()
            self._hide_viewport_menubar()

    def _do_hide_pass(self):
        try:
            import omni.ui as ui
            for w in ui.Workspace.get_windows():
                if w.title != "Viewport" and w.visible:
                    try:
                        w.visible = False
                    except Exception:
                        pass
        except Exception:
            pass

    def _hide_viewport_menubar(self):
        """Hide the viewport top menubar (Renderer, Display, Camera, Physics, etc.)
        by setting each registered ViewportMenubar's visible flag to False."""
        try:
            from omni.kit.viewport.menubar.core import get_instance
            instance = get_instance()
            if instance:
                for menubar in instance.get_menubars():
                    menubar.visible = False
        except Exception:
            pass

    def on_shutdown(self):
        """This is called every time the extension is deactivated."""
        # Cancel background tasks to avoid duplicates on reload
        for attr in ("_await_layout", "_load_layout_task", "_hide_non_viewport_task"):
            try:
                task = getattr(self, attr, None)
                if task is not None:
                    try:
                        task.cancel()
                    except Exception:
                        pass
            except Exception:
                pass
            setattr(self, attr, None)

        # Undo ImGui style push (prevents style stack growth on reload)
        try:
            if getattr(self, "_imgui_style_pushed", False):
                imgui = _imgui.acquire_imgui()
                try:
                    imgui.pop_style_var(1)
                except Exception:
                    pass
        except Exception:
            pass
        self._imgui_style_pushed = False

        return
