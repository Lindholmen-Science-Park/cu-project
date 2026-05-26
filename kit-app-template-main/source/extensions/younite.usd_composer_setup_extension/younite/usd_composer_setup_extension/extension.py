# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import asyncio
import inspect
import logging
import os
import platform
import subprocess
import sys
import webbrowser
from pathlib import Path


import carb
import omni.ext
import omni.kit.app
import omni.kit.commands
import omni.kit.menu.utils
import omni.kit.stage_templates as stage_templates
import omni.kit.ui
import omni.kit.window.property as property_window_ext
import omni.ui as ui
import omni.usd
from omni.kit.menu.utils import MenuLayout, MenuItemDescription
from omni.kit.property.usd import PrimPathWidget
from omni.kit.quicklayout import QuickLayout
from omni.kit.window.title import get_main_window_title

# USD Python API imports for asset generation
from pxr import Usd, UsdGeom, Gf

DATA_PATH = Path(carb.tokens.get_tokens_interface().resolve(
    "${younite.usd_composer_setup_extension}")
)


class AssetGenerator:
    """Asset Generator integrated into Composer setup extension."""
    
    def __init__(self):
        self.data_dir = self._find_data_directory()
        print(f"[AssetGenerator] Data directory: {self.data_dir}")

    def _find_data_directory(self):
        """Find the data directory relative to the extension."""
        try:
            # Try to use carb tokens to find the project root
            tokens = carb.tokens.get_tokens_interface()
            if tokens:
                # Try to resolve the project root
                project_root = tokens.resolve("${project}")
                if project_root and os.path.exists(project_root):
                    data_dir = os.path.join(project_root, "source", "data")
                    if os.path.exists(data_dir):
                        print(f"Found data directory via carb tokens: {data_dir}")
                        return data_dir
        except:
            pass
        
        # Fallback: Get the extension directory and try multiple paths
        ext_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        print(f"Extension directory: {ext_dir}")
        
        # Try multiple possible paths to find the source data directory
        possible_paths = [
            # From build directory to source (most likely)
            os.path.join(ext_dir, "..", "..", "..", "..", "source", "data"),
            # From source directory
            os.path.join(ext_dir, "..", "..", "source", "data"),
            # Direct path from project root
            os.path.join(os.path.dirname(ext_dir), "..", "..", "source", "data"),
            # Alternative build path
            os.path.join(ext_dir, "..", "..", "..", "source", "data"),
            # Try going up more levels from build
            os.path.join(ext_dir, "..", "..", "..", "..", "..", "source", "data"),
        ]
        
        for path in possible_paths:
            abs_path = os.path.abspath(path)
            print(f"Checking path: {abs_path}")
            if os.path.exists(abs_path):
                print(f"Found data directory at: {abs_path}")
                return abs_path
        
        # If none found, return the first attempt
        fallback_path = os.path.abspath(os.path.join(ext_dir, "..", "..", "..", "..", "source", "data"))
        print(f"Using fallback path: {fallback_path}")
        return fallback_path

    def get_lod_files(self, asset_folder):
        """Get all LOD files in the asset folder, sorted by LOD level."""
        import re
        lod_files = []
        for file in os.listdir(asset_folder):
            if file.endswith('.usdc'):
                # Check for LOD pattern: _lod0, _lod1, etc.
                lod_match = re.search(r'_lod(\d+)\.usdc$', file)
                if lod_match:
                    lod_level = int(lod_match.group(1))
                    lod_files.append((lod_level, file))
        
        # Sort by LOD level (0 = highest detail)
        lod_files.sort(key=lambda x: x[0])
        return lod_files

    def get_single_usdc_file(self, asset_folder):
        """Get the single .usdc file if no LOD files exist."""
        usdc_files = [f for f in os.listdir(asset_folder) if f.endswith('.usdc')]
        lod_files = [f for f in usdc_files if '_lod' in f]
        
        if not lod_files:  # No LOD files, return the single .usdc file
            return usdc_files[0] if usdc_files else None
        return None

    def extract_transforms_from_usdc(self, usdc_path):
        """Extract transform information from a USDC file using USD Python API."""
        try:
            print(f"  Reading transforms from: {os.path.basename(usdc_path)}")
            
            # Open the USDC file
            stage = Usd.Stage.Open(usdc_path)
            if not stage:
                print(f"  Warning: Could not open {usdc_path}")
                return self._get_default_transforms()
            
            print(f"  Stage opened successfully")
            
            # Get the default prim
            default_prim = stage.GetDefaultPrim()
            if not default_prim:
                print(f"  Warning: No default prim found in {usdc_path}")
                return self._get_default_transforms()
            
            print(f"  Default prim: {default_prim.GetPath()}")
            
            # Try to get xformable from default prim
            xformable = UsdGeom.Xformable(default_prim)
            if not xformable:
                print(f"  Warning: Default prim is not xformable")
                return self._get_default_transforms()
            
            # Get all xform operations
            xform_ops = xformable.GetOrderedXformOps()
            print(f"  Found {len(xform_ops)} xform operations")
            
            # Initialize default values
            translation = (0.0, 0.0, 0.0)
            rotation_euler = (0.0, 0.0, 0.0)
            scale = (1.0, 1.0, 1.0)
            
            # Read values from xformOps
            for op in xform_ops:
                op_name = op.GetOpName()
                op_value = op.Get()
                
                if op_value is not None:
                    print(f"    XformOp: {op_name} = {op_value}")
                    
                    if "translate" in op_name.lower():
                        if hasattr(op_value, '__len__') and len(op_value) >= 3:
                            translation = (float(op_value[0]), float(op_value[1]), float(op_value[2]))
                    elif "rotate" in op_name.lower() and "unitsResolve" not in op_name.lower():
                        if hasattr(op_value, '__len__') and len(op_value) >= 3:
                            rotation_euler = (float(op_value[0]), float(op_value[1]), float(op_value[2]))
                    elif "scale" in op_name.lower():
                        if hasattr(op_value, '__len__') and len(op_value) >= 3:
                            scale = (float(op_value[0]), float(op_value[1]), float(op_value[2]))
            
            # If we didn't find any meaningful transforms, try to get them from the world transform
            if (abs(translation[0]) < 0.001 and abs(translation[1]) < 0.001 and abs(translation[2]) < 0.001):
                print(f"  No translate found in xformOps, trying world transform...")
                try:
                    world_transform = xformable.ComputeLocalToWorldTransform(0.0)
                    world_translation = world_transform.ExtractTranslation()
                    if (abs(world_translation[0]) > 0.001 or abs(world_translation[1]) > 0.001 or abs(world_translation[2]) > 0.001):
                        translation = (world_translation[0], world_translation[1], world_translation[2])
                        print(f"    World transform translation: {translation}")
                except Exception as e:
                    print(f"    Error getting world transform: {e}")
            
            print(f"  Final extracted transforms:")
            print(f"    Translation: {translation}")
            print(f"    Rotation: {rotation_euler}")
            print(f"    Scale: {scale}")
            
            # No coordinate system conversion needed since UE export already converted Z-up to Y-up
            rotateX_unitsResolve = 0.0
            
            return {
                'translate': translation,
                'rotateXYZ': rotation_euler,
                'scale': scale,
                'rotateX_unitsResolve': rotateX_unitsResolve
            }
            
        except Exception as e:
            print(f"  Error reading transforms from {usdc_path}: {e}")
            import traceback
            traceback.print_exc()
            return self._get_default_transforms()

    def _get_default_transforms(self):
        """Return None to indicate no transforms should be applied."""
        return None

    def _sanitize_prim_name(self, asset_name):
        """Sanitize asset name to be a valid USD prim name."""
        import re
        
        # If the name starts with a number, prefix it with "Asset_"
        if asset_name[0].isdigit():
            sanitized = f"Asset_{asset_name}"
        else:
            sanitized = asset_name
        
        # Replace any invalid characters with underscores
        # USD prim names can contain letters, numbers, and underscores, but not start with numbers
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', sanitized)
        
        # Ensure it doesn't start with a number after sanitization
        if sanitized[0].isdigit():
            sanitized = f"Asset_{sanitized}"
        
        return sanitized

    def generate_simple_asset_usda(self, asset_name, usdc_file, asset_folder):
        """Generate a simple USD file for an asset with a single .usdc file."""
        sanitized_name = self._sanitize_prim_name(asset_name)
        usda_content = f'''#usda 1.0
(
    defaultPrim = "{sanitized_name}"
    metersPerUnit = 0.01
    upAxis = "Y"
)

def Xform "{sanitized_name}"
{{
    over "{sanitized_name}" (
        prepend payload = @{usdc_file}@
    )
    {{
    }}
}}
'''
        
        usda_path = os.path.join(asset_folder, f"{asset_name}.usda")
        with open(usda_path, 'w') as f:
            f.write(usda_content)
        
        return usda_path

    def generate_lod_asset_usda(self, asset_name, lod_files, asset_folder):
        """Generate a USD file for an asset with LOD variants."""
        sanitized_name = self._sanitize_prim_name(asset_name)
        usda_content = f'''#usda 1.0
(
    defaultPrim = "{sanitized_name}"
    metersPerUnit = 0.01
    upAxis = "Y"
)

def Xform "{sanitized_name}" (
    variants = {{
        string LOD = "LOD0"
    }}
    prepend variantSets = "LOD"
)
{{
    variantSet "LOD" = {{
        "LOD0" {{
            over "{sanitized_name}" (
                prepend payload = @{lod_files[0][1]}@
            )
            {{
            }}
        }}
'''
        
        # Add additional LOD variants
        for lod_level, lod_file in lod_files[1:]:
            usda_content += f'''        "LOD{lod_level}" {{
            over "{sanitized_name}" (
                prepend payload = @{lod_file}@
            )
            {{
            }}
        }}
'''
        
        usda_content += '''    }
}
'''
        
        usda_path = os.path.join(asset_folder, f"{asset_name}.usda")
        with open(usda_path, 'w') as f:
            f.write(usda_content)
        
        return usda_path

    def update_main_scene_usda(self, asset_name, usda_relative_path, transforms):
        """Update main_scene.usda to include the new asset reference."""
        main_scene_path = os.path.join(self.data_dir, "scenes", "main_scene.usda")
        print(f"Looking for main_scene.usda at: {main_scene_path}")
        
        if not os.path.exists(main_scene_path):
            print(f"Warning: {main_scene_path} not found. Skipping main_scene.usda update.")
            return
        
        # Sanitize the asset name for USD prim names
        sanitized_name = self._sanitize_prim_name(asset_name)
        print(f"Using sanitized prim name: '{sanitized_name}' for asset '{asset_name}'")
        
        # Read the current main_scene.usda content
        with open(main_scene_path, 'r') as f:
            content = f.read()
        
        # Check if the asset is already referenced (check both original and sanitized names)
        if f'def "{asset_name}"' in content or f'def "{sanitized_name}"' in content:
            print(f"Asset '{asset_name}' (sanitized: '{sanitized_name}') already exists in main_scene.usda. Skipping.")
            return
        
        # Find the insertion point (after the last asset definition in World)
        import re
        world_end_pattern = r'(def "lighting_2".*?\{.*?\})'
        match = re.search(world_end_pattern, content, re.DOTALL)
        
        if match:
            # Insert the new asset before lighting_2
            insertion_point = match.start()
            
            if transforms:
                # Asset has transforms, include them
                new_asset_def = f'''
    def "{sanitized_name}" (
        prepend references = @{usda_relative_path}@
    )
    {{
        double xformOp:rotateX:unitsResolve = {transforms['rotateX_unitsResolve']}
        float3 xformOp:rotateXYZ = {transforms['rotateXYZ']}
        float3 xformOp:scale = {transforms['scale']}
        double3 xformOp:translate = {transforms['translate']}
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale", "xformOp:rotateX:unitsResolve"]
    }}

'''
            else:
                # Asset has no transforms, just reference it
                new_asset_def = f'''
    def "{sanitized_name}" (
        prepend references = @{usda_relative_path}@
    )
    {{
    }}

'''
            
            # Insert the new asset definition
            new_content = content[:insertion_point] + new_asset_def + content[insertion_point:]
            
            # Write the updated content
            with open(main_scene_path, 'w') as f:
                f.write(new_content)
            
            print(f"Added '{sanitized_name}' to main_scene.usda (original name: '{asset_name}')")
        else:
            print(f"Could not find insertion point in main_scene.usda for '{asset_name}'")

    def process_asset_folder(self, asset_folder_path):
        """Process a single asset folder and generate the appropriate USD file."""
        asset_name = os.path.basename(asset_folder_path)
        print(f"Processing asset: {asset_name}")
        
        # Check if .usda file already exists - if so, skip to preserve manual modifications
        usda_path = os.path.join(asset_folder_path, f"{asset_name}.usda")
        if os.path.exists(usda_path):
            print(f"  Skipping {asset_name} - .usda file already exists (preserving manual modifications)")
            return usda_path
        
        # Check for LOD files first
        lod_files = self.get_lod_files(asset_folder_path)
        
        if lod_files:
            print(f"  Found {len(lod_files)} LOD files: {[f[1] for f in lod_files]}")
            usda_path = self.generate_lod_asset_usda(asset_name, lod_files, asset_folder_path)
            print(f"  Generated LOD asset: {usda_path}")
        else:
            # Check for single .usdc file
            single_file = self.get_single_usdc_file(asset_folder_path)
            if single_file:
                print(f"  Found single .usdc file: {single_file}")
                usda_path = self.generate_simple_asset_usda(asset_name, single_file, asset_folder_path)
                print(f"  Generated simple asset: {usda_path}")
            else:
                print(f"  No .usdc files found in {asset_folder_path}")
                return None
        
        # Extract transforms directly from the USDC file
        transforms = None
        if lod_files:
            # For LOD assets, try to extract from the first LOD file
            first_lod_path = os.path.join(asset_folder_path, lod_files[0][1])
            transforms = self.extract_transforms_from_usdc(first_lod_path)
        else:
            # For single file assets, extract from the single file
            single_file = self.get_single_usdc_file(asset_folder_path)
            if single_file:
                single_file_path = os.path.join(asset_folder_path, single_file)
                transforms = self.extract_transforms_from_usdc(single_file_path)
        
        if not transforms:
            print(f"  Warning: No transforms found for {asset_name}, asset will be placed at origin")
        
        # Calculate relative path from main_scene.usda to the generated .usda file
        usda_relative_path = f"../Assets/{asset_name}/{asset_name}.usda"
        
        # Update main_scene.usda
        self.update_main_scene_usda(asset_name, usda_relative_path, transforms)
        
        return usda_path


    def generate_assets(self):
        """Main function to process all assets in the Assets folder."""
        assets_folder = os.path.join(self.data_dir, "Assets")
        
        print(f"Looking for Assets folder at: {assets_folder}")
        print(f"Data directory: {self.data_dir}")
        print(f"Data directory exists: {os.path.exists(self.data_dir)}")
        
        if not os.path.exists(assets_folder):
            print(f"Assets folder '{assets_folder}' not found.")
            # Try alternative paths
            alt_paths = [
                os.path.join(self.data_dir, "..", "Assets"),
                os.path.join(self.data_dir, "..", "..", "Assets"),
                os.path.join(os.path.dirname(self.data_dir), "Assets")
            ]
            for alt_path in alt_paths:
                alt_path = os.path.abspath(alt_path)
                print(f"Trying alternative path: {alt_path}")
                if os.path.exists(alt_path):
                    print(f"Found Assets folder at: {alt_path}")
                    assets_folder = alt_path
                    break
            else:
                return False
        
        print(f"Scanning Assets folder: {assets_folder}")
        
        # Get all subdirectories in Assets folder
        asset_folders = [d for d in os.listdir(assets_folder) 
                        if os.path.isdir(os.path.join(assets_folder, d))]
        
        if not asset_folders:
            print("No asset folders found in Assets directory.")
            return False
        
        print(f"Found {len(asset_folders)} asset folders: {asset_folders}")
        
        # Process each asset folder
        success_count = 0
        for asset_folder in asset_folders:
            asset_path = os.path.join(assets_folder, asset_folder)
            try:
                result = self.process_asset_folder(asset_path)
                if result:
                    success_count += 1
            except Exception as e:
                print(f"Error processing {asset_folder}: {e}")
        
        print(f"Asset generation complete! Successfully processed {success_count}/{len(asset_folders)} assets.")
        return success_count > 0


async def _load_layout(layout_file: str, keep_windows_open=False):
    """Loads a provided layout file and ensures the viewport is set to FILL."""
    try:
        # few frames delay to avoid the conflict with the
        # layout of omni.kit.mainwindow
        for _ in range(3):
            await omni.kit.app.get_app().next_update_async()
        QuickLayout.load_file(layout_file, keep_windows_open)
    except:
        QuickLayout.load_file(layout_file)


class CreateSetupExtension(omni.ext.IExt):
    """Create Final Configuration"""
    def on_startup(self, _ext_id):
        """
        setup the window layout, menu, final configuration
        of the extensions etc
        """
        self._settings = carb.settings.get_settings()
        if self._settings and self._settings.get("/app/warmupMode"):
            # if warmup mode is enabled, we don't want to load the stage or
            # layout, just return
            return

        self._menu_layout = []
        self._asset_generator = AssetGenerator()

        telemetry_logger = logging.getLogger("idl.telemetry.opentelemetry")
        telemetry_logger.setLevel(logging.ERROR)

        # this is a work around as some Extensions don't properly setup their
        # default setting in time
        self._set_defaults()

        # adjust couple of viewport settings
        self._settings.set("/app/viewport/boundingBoxes/enabled", True)

        # These two settings do not co-operate well on ADA cards, so for
        # now simulate a toggle of the present thread on startup to work around
        if self._settings.get("/exts/omni.kit.renderer.core/present/enabled") \
            and self._settings.get(
            "/exts/omni.kit.widget.viewport/autoAttach/mode"
        ):
            async def _toggle_present(settings, n_waits: int = 1):
                async def _toggle_setting(app, enabled: bool, n_waits: int):
                    for _ in range(n_waits):
                        await app.next_update_async()
                    settings.set(
                        "/exts/omni.kit.renderer.core/present/enabled",
                        enabled
                    )

                app = omni.kit.app.get_app()
                await _toggle_setting(app, False, n_waits)
                await _toggle_setting(app, True, n_waits)

            asyncio.ensure_future(_toggle_present(self._settings))

        # Setting and Saving FSD as a global change in preferences
        # Requires to listen for changes at the local path to update
        # Composer's persistent path.
        fabric_app_setting = self._settings.get("/app/useFabricSceneDelegate")
        fabric_persistent_setting = self._settings.get(
            "/persistent/app/useFabricSceneDelegate"
        )
        fabric_enabled: bool = fabric_app_setting if \
            fabric_persistent_setting is None else fabric_persistent_setting

        self._settings.set("/app/useFabricSceneDelegate", fabric_enabled)

        self._sub_fabric_delegate_changed = \
            omni.kit.app.SettingChangeSubscription(
                "/app/useFabricSceneDelegate",
                self._on_fabric_delegate_changed
            )

        # Adjust the Window Title to show the Create Version
        window_title = get_main_window_title()

        app_version = self._settings.get("/app/version")
        if not app_version:
            with open(
                carb.tokens.get_tokens_interface().resolve("${app}/../VERSION"),
                encoding="utf-8"
            ) as f:
                app_version = f.read()

        if app_version:
            if "+" in app_version:
                app_version, _ = app_version.split("+")

            # for RC version we remove some details
            if self._settings.get("/privacy/externalBuild"):
                if "-" in app_version:
                    app_version, _ = app_version.split("-")
                window_title.set_app_version(app_version)
            else:
                window_title.set_app_version(app_version)

        imgui_style_applied = False
        try:
            # using imgui directly to adjust some color and Variable
            import omni.kit.imgui as _imgui
            imgui = _imgui.acquire_imgui()
            if imgui.is_valid():
                imgui.push_style_color(_imgui.StyleColor.ScrollbarGrab, carb.Float4(0.4, 0.4, 0.4, 1))
                imgui.push_style_color(_imgui.StyleColor.ScrollbarGrabHovered, carb.Float4(0.6, 0.6, 0.6, 1))
                imgui.push_style_color(_imgui.StyleColor.ScrollbarGrabActive, carb.Float4(0.8, 0.8, 0.8, 1))
                imgui.push_style_var_float(_imgui.StyleVar.DockSplitterSize, 2)
                imgui_style_applied = True
        except ImportError:
            pass

        if not imgui_style_applied:
            carb.log_error("Style may not be as expected (carb.imgui was not valid)")

        layout_file = f"{DATA_PATH}/layouts/default.json"

        # Setting to hack few things in test run. Ideally we shouldn't need it.
        test_mode = self._settings.get("/app/testMode")

        if not test_mode:
            asyncio.ensure_future(_load_layout(layout_file, True))

        asyncio.ensure_future(self.__property_window())

        self.__menu_update()

        if not test_mode and not \
                self._settings.get("/app/content/emptyStageOnStart"):
            asyncio.ensure_future(self.__new_stage())

        startup_time = \
            omni.kit.app.get_app_interface().get_time_since_start_s()
        self._settings.set(
            "/crashreporter/data/startup_time", f"{startup_time}"
        )

        def show_documentation(*args):
            webbrowser.open(
                "https://docs.omniverse.nvidia.com/composer/latest/index.html"
            )
        
        def generate_assets(*args):
            """Generate assets with USD API support."""
            try:
                print("Running Asset Generator with USD API...")
                success = self._asset_generator.generate_assets()
                
                if success:
                    print("Asset generation completed successfully! Reloading scene...")
                    # Reload the mastah.usda file
                    _reload_mastah_scene()
                    
                else:
                    print("Asset generation failed!")
                    
            except Exception as e:
                print(f"Asset generation error: {str(e)}")
        
        def _reload_mastah_scene():
            """Reload the mastah.usda scene."""
            try:
                # Get the current stage
                stage = omni.usd.get_context().get_stage()
                if stage:
                    # Get the current file path
                    current_file = stage.GetRootLayer().identifier
                    
                    # Try to find and open mastah.usda
                    mastah_path = os.path.join(self._asset_generator.data_dir, "mastah.usda")
                    if os.path.exists(mastah_path):
                        # Use the USD context to open the file
                        omni.usd.get_context().open_stage(mastah_path)
                        print(f"Reloaded mastah.usda from: {mastah_path}")
                    else:
                        print(f"Could not find mastah.usda at: {mastah_path}")
                            
            except Exception as e:
                print(f"Error reloading scene: {e}")
        
        self._help_menu_items = [
            MenuItemDescription(
                name="Documentation",
                onclick_fn=show_documentation,
                appear_after=[omni.kit.menu.utils.MenuItemOrder.FIRST]
            )
        ]
        omni.kit.menu.utils.add_menu_items(self._help_menu_items, name="Help")
        
        def capture_current_transforms(*args):
            """Capture current transform values from selected object for config file."""
            try:
                import omni.usd
                import json
                
                # Get the current stage
                stage = omni.usd.get_context().get_stage()
                if not stage:
                    print("No stage available")
                    return
                
                # Get the selected prim
                selection = omni.usd.get_context().get_selection()
                if not selection.get_selected_prim_paths():
                    print("No object selected. Please select an object to capture its transforms.")
                    return
                
                selected_path = selection.get_selected_prim_paths()[0]
                prim = stage.GetPrimAtPath(selected_path)
                
                if not prim:
                    print(f"Could not find prim at {selected_path}")
                    return
                
                # Get the transform values
                xformable = UsdGeom.Xformable(prim)
                if xformable:
                    # Get the local transform
                    transform = xformable.ComputeLocalToWorldTransform(0.0)
                    translation = transform.ExtractTranslation()
                    
                    # Get xform operations
                    xform_ops = xformable.GetOrderedXformOps()
                    rotateX_unitsResolve = 0
                    rotateXYZ = (0, 0, 0)
                    scale = (1, 1, 1)
                    
                    for op in xform_ops:
                        op_name = op.GetOpName()
                        if "rotateX:unitsResolve" in op_name:
                            rotateX_unitsResolve = op.Get() or 0
                        elif "rotateXYZ" in op_name:
                            rotateXYZ = op.Get() or (0, 0, 0)
                        elif "scale" in op_name:
                            scale = op.Get() or (1, 1, 1)
                    
                    # Create transform data
                    transform_data = {
                        'translate': [translation[0], translation[1], translation[2]],
                        'rotateXYZ': [rotateXYZ[0], rotateXYZ[1], rotateXYZ[2]],
                        'scale': [scale[0], scale[1], scale[2]],
                        'rotateX_unitsResolve': rotateX_unitsResolve
                    }
                    
                    # Print the JSON for easy copying
                    print("=" * 50)
                    print("CAPTURED TRANSFORM DATA:")
                    print("=" * 50)
                    print(f'"{prim.GetName().lower()}": {{')
                    print(f'    "translate": {transform_data["translate"]},')
                    print(f'    "rotateXYZ": {transform_data["rotateXYZ"]},')
                    print(f'    "scale": {transform_data["scale"]},')
                    print(f'    "rotateX_unitsResolve": {transform_data["rotateX_unitsResolve"]}')
                    print('}')
                    print("=" * 50)
                    print("Copy this data to asset_transforms.json")
                    
            except Exception as e:
                print(f"Error capturing transforms: {e}")
        
        # Add Asset Generator menu items
        self._asset_generator_menu_items = [
            MenuItemDescription(
                name="Generate Assets",
                onclick_fn=generate_assets,
                appear_after=[omni.kit.menu.utils.MenuItemOrder.FIRST]
            ),
            MenuItemDescription(
                name="Capture Selected Transforms",
                onclick_fn=capture_current_transforms,
                appear_after=[omni.kit.menu.utils.MenuItemOrder.FIRST]
            )
        ]
        omni.kit.menu.utils.add_menu_items(self._asset_generator_menu_items, name="Tools")

    def _set_defaults(self):
        """
        This is trying to setup some defaults for extensions to avoid warnings.
        """
        self._settings.set_default("/persistent/app/omniverse/bookmarks", {})
        self._settings.set_default(
            "/persistent/app/stage/timeCodeRange", [0, 100]
        )

        self._settings.set_default(
            "/persistent/audio/context/closeAudioPlayerOnStop",
            False
        )

        self._settings.set_default(
            "/persistent/app/primCreation/PrimCreationWithDefaultXformOps",
            True
        )
        self._settings.set_default(
            "/persistent/app/primCreation/DefaultXformOpType",
            "Scale, Rotate, Translate"
        )
        self._settings.set_default(
            "/persistent/app/primCreation/DefaultRotationOrder",
            "ZYX"
        )
        self._settings.set_default(
            "/persistent/app/primCreation/DefaultXformOpPrecision",
            "Double"
        )

        # omni.kit.property.tagging
        self._settings.set_default(
            "/persistent/exts/omni.kit.property.tagging/showAdvancedTagView",
            False
        )
        self._settings.set_default(
            "/persistent/exts/omni.kit.property.tagging/showHiddenTags",
            False
        )
        self._settings.set_default(
            "/persistent/exts/omni.kit.property.tagging/modifyHiddenTags",
            False
        )

        self._settings.set_default(
            "/rtx/sceneDb/ambientLightIntensity", 0.0
        )  # set default ambientLight intensity to Zero

    def _on_fabric_delegate_changed(
            self, _v: str, event_type: carb.settings.ChangeEventType):
        if event_type == carb.settings.ChangeEventType.CHANGED:
            enabled: bool = self._settings.get_as_bool(
                "/app/useFabricSceneDelegate"
            )
            self._settings.set(
                "/persistent/app/useFabricSceneDelegate", enabled
            )

    async def __new_stage(self):
        """Create a new stage """
        # 5 frame delay to allow Layout
        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()

        if omni.usd.get_context().can_open_stage():
            stage_templates.new_stage(template=None)

    def _launch_app(self, app_id, console=True, custom_args=None):
        """launch another Kit app with the same settings"""
        app_path = carb.tokens.get_tokens_interface().resolve("${app}")
        kit_file_path = os.path.join(app_path, app_id)

        # https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
        # Validate input from command line (detected in static analysis)
        kit_exe = sys.argv[0]
        if not os.path.exists(kit_exe):
            print(f"cannot find executable{kit_exe}")
            return

        launch_args = [kit_exe]
        launch_args += [kit_file_path]
        if custom_args:
            launch_args.extend(custom_args)

        # Pass all exts folders
        exts_folders = self._settings.get("/app/exts/folders")
        if exts_folders:
            for folder in exts_folders:
                launch_args.extend(["--ext-folder", folder])

        kwargs = {"close_fds": False}
        if platform.system().lower() == "windows":
            if console:
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE | \
                    subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(launch_args, **kwargs)

    def _show_ui_docs(self):
        """show the omniverse ui documentation as an external Application"""
        self._launch_app("omni.app.uidoc.kit")

    def _show_launcher(self):
        """show the omniverse ui documentation as an external Application"""
        self._launch_app(
            "omni.create.launcher.kit",
            console=False,
            custom_args={"--/app/auto_launch=false"}
        )

    async def __property_window(self):
        """Creates a propety window and sets column sizes."""
        await omni.kit.app.get_app().next_update_async()

        property_window = property_window_ext.get_window()
        property_window.set_scheme_delegate_layout(
            "Create Layout",
            ["basis_curves_prim", "path_prim", "material_prim",
             "xformable_prim", "shade_prim", "camera_prim"],
        )

        # expand width of path_items so "Instancable" doesn't get wrapped
        PrimPathWidget.set_path_item_padding(3.5)

    def __menu_update(self):
        """Update the menu"""
        self._menu_layout = [
            MenuLayout.Menu(
                "Window",
                [
                    MenuLayout.SubMenu(
                        "Animation",
                        [
                            MenuLayout.Item("Timeline"),
                            MenuLayout.Item("Sequencer"),
                            MenuLayout.Item("Curve Editor"),
                            MenuLayout.Item("Retargeting"),
                            MenuLayout.Item("Animation Graph"),
                            MenuLayout.Item("Animation Graph Samples"),
                        ],
                    ),
                    MenuLayout.SubMenu(
                        "Layout",
                        [
                            MenuLayout.Item("Quick Save", remove=True),
                            MenuLayout.Item("Quick Load", remove=True),
                        ],
                    ),
                    MenuLayout.SubMenu(
                        "Browsers",
                        [
                            MenuLayout.Item("Content", source="Window/Content"),
                            MenuLayout.Item("Materials"),
                            MenuLayout.Item("Skies"),
                        ],
                    ),
                    MenuLayout.SubMenu(
                        "Rendering",
                        [
                            MenuLayout.Item("Render Settings"),
                            MenuLayout.Item("Movie Capture"),
                            MenuLayout.Item("MDL Material Graph"),
                            MenuLayout.Item("Tablet XR"),
                        ],
                    ),
                    MenuLayout.SubMenu(
                        "Utilities",
                        [
                            MenuLayout.Item("Console"),
                            MenuLayout.Item("Profiler"),
                            MenuLayout.Item("USD Paths"),
                            MenuLayout.Item("Statistics"),
                            MenuLayout.Item("Activity Progress"),
                            MenuLayout.Item("Actions"),
                            MenuLayout.Item("Asset Validator"),
                        ],
                    ),
                    MenuLayout.Sort(
                        exclude_items=["Extensions"], sort_submenus=True
                    ),
                    MenuLayout.Item("New Viewport Window", remove=True),
                ],
            ),
            MenuLayout.Menu(
                "Layout",
                [
                    MenuLayout.Item("Default", source="Reset Layout"),
                    MenuLayout.Seperator(),
                    MenuLayout.Item(
                        "UI Toggle Visibility",
                        source="Window/UI Toggle Visibility"
                    ),
                    MenuLayout.Item(
                        "Fullscreen Mode", source="Window/Fullscreen Mode"
                    ),
                    MenuLayout.Seperator(),
                    MenuLayout.Item(
                        "Save Layout", source="Window/Layout/Save Layout..."
                    ),
                    MenuLayout.Item(
                        "Load Layout", source="Window/Layout/Load Layout..."
                    ),
                    MenuLayout.Seperator(),
                    MenuLayout.Item(
                        "Quick Save", source="Window/Layout/Quick Save"
                    ),
                    MenuLayout.Item(
                        "Quick Load", source="Window/Layout/Quick Load"
                    ),
                ],
            ),
        ]
        omni.kit.menu.utils.add_layout(self._menu_layout)

        self._layout_menu_items = []

        def add_layout_menu_entry(name, parameter, key):
            """Add a layout menu entry."""
            if inspect.isfunction(parameter):
                menu_dict = omni.kit.menu.utils.build_submenu_dict(
                    [
                        MenuItemDescription(name=f"Layout/{name}",
                                            onclick_fn=lambda: asyncio.ensure_future(parameter()),
                                            hotkey=(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL, key)),
                    ]
                )
            else:
                async def _active_layout(layout):
                    await _load_layout(layout)
                    # load layout file again to make sure layout correct
                    await _load_layout(layout)

                menu_dict = omni.kit.menu.utils.build_submenu_dict(
                    [
                        MenuItemDescription(name=f"Layout/{name}",
                                            onclick_fn=lambda: asyncio.ensure_future(_active_layout(f"{DATA_PATH}/layouts/{parameter}.json")),
                                            hotkey=(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL, key)),
                    ]
                )

            # add menu
            for group in menu_dict:
                omni.kit.menu.utils.add_menu_items(menu_dict[group], group)

            self._layout_menu_items.append(menu_dict)

        add_layout_menu_entry(
            "Reset Layout", "default", carb.input.KeyboardInput.KEY_1
        )

        # create Quick Load & Quick Save
        async def quick_save():
            QuickLayout.quick_save(None, None)

        async def quick_load():
            QuickLayout.quick_load(None, None)

        add_layout_menu_entry(
            "Quick Save", quick_save, carb.input.KeyboardInput.KEY_7
        )
        add_layout_menu_entry(
            "Quick Load", quick_load, carb.input.KeyboardInput.KEY_8
        )

        # open "Asset Stores" window
        ui.Workspace.show_window("Asset Stores")

    def on_shutdown(self):
        """Clean up the extension"""
        self._sub_fabric_delegate_changed = None

        omni.kit.menu.utils.remove_layout(self._menu_layout)
        self._menu_layout = None

        for menu_dict in self._layout_menu_items:
            for group in menu_dict:
                omni.kit.menu.utils.remove_menu_items(menu_dict[group], group)

        self._layout_menu_items = None
        self._launcher_menu = None
        self._reset_menu = None
        
        # Clean up asset generator menu items
        if hasattr(self, '_asset_generator_menu_items'):
            omni.kit.menu.utils.remove_menu_items(self._asset_generator_menu_items, name="Tools")
            self._asset_generator_menu_items = None
